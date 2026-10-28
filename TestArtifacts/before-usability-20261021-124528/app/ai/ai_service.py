from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any

from app.ai.ai_cache import AIResponseCache
from app.ai.evidence_store import AIEvidenceStore
from app.ai.knowledge_store import LocalKnowledgeStore
from app.ai.prompt_manager import get_prompt
from app.ai.qwen_runtime import QwenClient, QwenRuntimeManager
from app.ai.structured_output import clamp_confidence
from app.core.cache_db import initialize_database
from app.utils.config import DB_PATH
from app.utils.logger import logger


@dataclass(slots=True)
class AIServiceConfig:
    enabled: bool = True
    start_on_demand: bool = True
    cache_enabled: bool = True
    cache_days: int = 180
    minimum_confidence: float = 0.75
    max_prompt_chars: int = 12000
    max_parallel_calls: int = 1
    request_timeout: float = 90.0


class LocalAIService:
    """Lightweight coordinator for optional local Qwen features.

    - Qwen is never imported as a heavyweight Python ML dependency.
    - The server is contacted over localhost through its OpenAI-compatible API.
    - Calls are deduplicated by a SQLite cache.
    - A small semaphore prevents local-model request floods.
    """

    def __init__(self, runtime: QwenRuntimeManager, config: AIServiceConfig | None = None) -> None:
        self.runtime = runtime
        self.config = config or AIServiceConfig()
        self.cache = AIResponseCache()
        self.knowledge = LocalKnowledgeStore()
        self.evidence = AIEvidenceStore()
        self._semaphore = threading.BoundedSemaphore(max(1, int(self.config.max_parallel_calls)))
        self._client: QwenClient | None = None
        self._lock = threading.RLock()

    def reconfigure(self, config: AIServiceConfig) -> None:
        with self._lock:
            self.config = config
            self._semaphore = threading.BoundedSemaphore(max(1, int(config.max_parallel_calls)))
            self._client = None

    def _ensure_ready(self) -> None:
        if not self.config.enabled:
            raise RuntimeError("Local AI features are disabled in Settings.")
        if self.runtime.probe(timeout=0.2):
            return
        if not self.config.start_on_demand:
            raise RuntimeError("Qwen is not running. Start it from Home or Settings.")
        info = self.runtime.start(wait_seconds=12.0)
        if not info.reachable:
            raise RuntimeError(info.message or "Qwen could not be started.")

    def _get_client(self) -> QwenClient:
        with self._lock:
            if self._client is None:
                self._client = QwenClient(self.runtime.host, self.runtime.port, timeout=self.config.request_timeout)
            return self._client

    @staticmethod
    def _max_confidence(result: dict[str, Any]) -> float:
        values: list[float] = []
        if "confidence" in result:
            values.append(clamp_confidence(result.get("confidence")))
        for item in result.get("rules", []) if isinstance(result.get("rules"), list) else []:
            if isinstance(item, dict):
                values.append(clamp_confidence(item.get("confidence")))
        for item in result.get("suggestions", {}).values() if isinstance(result.get("suggestions"), dict) else []:
            if isinstance(item, dict):
                values.append(clamp_confidence(item.get("confidence")))
        return max(values, default=0.0)

    def run_json(self, task: str, payload: dict[str, Any], *, use_cache: bool = True, extra_instruction: str = "") -> dict[str, Any]:
        spec = get_prompt(task)
        clipped_payload = self._clip_payload(payload)
        if self.config.cache_enabled and use_cache:
            cached = self.cache.get(task=task, prompt_version=spec.version, payload=clipped_payload, max_age_days=self.config.cache_days)
            if cached is not None:
                cached = dict(cached)
                cached["_cache_hit"] = True
                return cached

        started = time.perf_counter()
        status = "completed"
        qwen_calls = 0
        try:
            self._ensure_ready()
            with self._semaphore:
                qwen_calls = 1
                messages = [
                    {"role": "system", "content": spec.system},
                    {
                        "role": "user",
                        "content": f"{spec.instruction}\n{extra_instruction}\nINPUT JSON:\n{json.dumps(clipped_payload, ensure_ascii=False, default=str)}",
                    },
                ]
                result = self._get_client().json_chat(messages, temperature=0.05, max_tokens=2400)
            if not isinstance(result, dict):
                raise ValueError("Qwen returned an invalid structured response")
            result["_prompt_version"] = spec.version
            result["_cache_hit"] = False
            confidence = self._max_confidence(result)
            if self.config.cache_enabled and use_cache:
                self.cache.set(task=task, prompt_version=spec.version, payload=clipped_payload, response=result, confidence=confidence)
            return result
        except Exception:
            status = "failed"
            raise
        finally:
            self._record_run(task, qwen_calls=qwen_calls, duration_ms=int((time.perf_counter() - started) * 1000), status=status)

    def _clip_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw = json.dumps(payload, ensure_ascii=False, default=str)
        limit = max(2000, int(self.config.max_prompt_chars))
        if len(raw) <= limit:
            return payload
        # Keep the payload valid and explicit about truncation rather than cutting JSON mid-token.
        return {
            "truncated": True,
            "original_chars": len(raw),
            "content": raw[:limit],
        }

    def _record_run(self, task: str, *, qwen_calls: int, duration_ms: int, status: str) -> None:
        initialize_database()
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO ai_runs(task, item_count, cache_hits, qwen_calls, duration_ms, status, details_json) VALUES (?, 1, 0, ?, ?, ?, '{}')",
                    (task, int(qwen_calls), int(duration_ms), status),
                )
                conn.commit()
        except Exception:
            logger.exception("Could not record local AI run")

    def clear_cache(self) -> int:
        return self.cache.clear()
