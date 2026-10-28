from __future__ import annotations

import json
import os
import socket
import subprocess
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable

import httpx

from app.utils.config import APPLICATION_DIR, LOG_DIR, PROJECT_ROOT
from app.utils.logger import logger

PORTABLE_CANDIDATES = (
    APPLICATION_DIR / "runtime" / "qwen",
    APPLICATION_DIR / "LLAMA",
    PROJECT_ROOT / "runtime" / "qwen",
    PROJECT_ROOT / "LLAMA",
)


@dataclass(slots=True)
class QwenRuntimeInfo:
    folder: str = ""
    executable: str = ""
    model: str = ""
    backend: str = "unknown"
    host: str = "127.0.0.1"
    port: int = 8080
    running: bool = False
    reachable: bool = False
    pid: int | None = None
    message: str = "Not configured"

    def to_dict(self) -> dict:
        return asdict(self)


class QwenRuntimeManager:
    """Discover, start, stop and probe a local Qwen llama.cpp/llamafile server.

    The manager does not assume a specific user profile. Portable runtimes beside
    the app are the default, with the user's explicit saved folder taking priority.
    """

    def __init__(
        self,
        *,
        folder: str | Path | None = None,
        executable: str | Path | None = None,
        model: str | Path | None = None,
        host: str = "127.0.0.1",
        port: int = 8080,
        extra_args: str = "",
    ) -> None:
        self.folder = Path(folder).expanduser() if str(folder or "").strip() else None
        self.executable_override = Path(executable).expanduser() if str(executable or "").strip() else None
        self.model_override = Path(model).expanduser() if str(model or "").strip() else None
        self.host = host or "127.0.0.1"
        self.port = int(port or 8080)
        self.extra_args = str(extra_args or "").strip()
        self._process: subprocess.Popen | None = None
        self._log_file = None
        self._lock = threading.RLock()
        self._last_info = QwenRuntimeInfo(host=self.host, port=self.port)
        self._asset_cache: tuple[str, str, str, str] | None = None
        self._resolved_folder_cache: Path | None = None

    @staticmethod
    def _existing_folder(candidates: Iterable[Path]) -> Path | None:
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_dir():
                    return candidate.resolve()
            except OSError:
                continue
        return None

    @staticmethod
    def _folder_has_runtime_assets(folder: Path) -> bool:
        try:
            if any(folder.rglob("*.gguf")):
                return True
            for pattern in ("llama-server*.exe", "llamafile*.exe", "llama*.exe"):
                if any(folder.glob(pattern)):
                    return True
        except OSError:
            return False
        return False

    def resolve_folder(self) -> Path | None:
        if self._resolved_folder_cache is not None:
            try:
                if self._resolved_folder_cache.exists() and self._resolved_folder_cache.is_dir():
                    return self._resolved_folder_cache
            except OSError:
                self._resolved_folder_cache = None

        saved = self.folder
        candidates: list[Path] = []
        if saved is not None:
            candidates.append(saved)
        candidates.extend(PORTABLE_CANDIDATES)
        existing: list[Path] = []
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_dir():
                    resolved = candidate.resolve()
                    existing.append(resolved)
                    if self._folder_has_runtime_assets(resolved):
                        self._resolved_folder_cache = resolved
                        return resolved
            except OSError:
                continue
        if saved is not None:
            try:
                if saved.exists() and saved.is_dir():
                    self._resolved_folder_cache = saved.resolve()
                    return self._resolved_folder_cache
            except OSError:
                pass
        if existing:
            self._resolved_folder_cache = existing[0]
            return existing[0]
        return None

    @staticmethod
    def _find_executable(folder: Path) -> tuple[Path | None, str]:
        explicit_names = [
            "llama-server.exe",
            "llama-server",
            "server.exe",
            "llamafile.exe",
            "llamafile",
        ]
        for name in explicit_names:
            path = folder / name
            if path.exists() and path.is_file():
                backend = "llama-server" if "llama-server" in name else "llamafile"
                return path.resolve(), backend

        patterns = ["llama-server*.exe", "llamafile*.exe", "llama*.exe", "*.exe"]
        for pattern in patterns:
            matches = sorted(folder.glob(pattern))
            for path in matches:
                lower = path.name.lower()
                if any(token in lower for token in ("server", "llama", "llamafile")):
                    backend = "llama-server" if "server" in lower and "llamafile" not in lower else "llamafile"
                    return path.resolve(), backend
        return None, "unknown"

    @staticmethod
    def _find_model(folder: Path) -> Path | None:
        models = sorted(
            folder.rglob("*.gguf"),
            key=lambda p: (
                0 if "qwen" in p.name.lower() else 1,
                0 if "instruct" in p.name.lower() else 1,
                p.name.lower(),
            ),
        )
        return models[0].resolve() if models else None

    def discover(self, *, probe: bool = True, refresh_assets: bool = False) -> QwenRuntimeInfo:
        folder = self.resolve_folder()
        if folder is None:
            info = QwenRuntimeInfo(host=self.host, port=self.port, message="Qwen folder not found")
            self._last_info = info
            return info

        cache_key = str(folder)
        exe = None
        backend = "unknown"
        model = None
        if self._asset_cache and not refresh_assets and self._asset_cache[0] == cache_key:
            _, exe_text, model_text, backend = self._asset_cache
            exe = Path(exe_text) if exe_text else None
            model = Path(model_text) if model_text else None
        else:
            if self.executable_override and self.executable_override.exists():
                exe = self.executable_override.resolve()
                lower = exe.name.lower()
                backend = "llama-server" if "server" in lower and "llamafile" not in lower else "llamafile"
            else:
                exe, backend = self._find_executable(folder)
            model = self.model_override.resolve() if self.model_override and self.model_override.exists() else self._find_model(folder)
            self._asset_cache = (cache_key, str(exe or ""), str(model or ""), backend)

        running = bool(self._process and self._process.poll() is None)
        reachable = self.probe(timeout=0.25) if probe else False

        if not exe:
            message = "No llama-server/llamafile executable found"
        elif not model:
            message = "No .gguf model found"
        elif reachable:
            message = "Qwen server is ready"
        elif running:
            message = "Qwen process is starting"
        else:
            message = "Qwen runtime ready to start"

        info = QwenRuntimeInfo(
            folder=str(folder),
            executable=str(exe or ""),
            model=str(model or ""),
            backend=backend,
            host=self.host,
            port=self.port,
            running=running,
            reachable=reachable,
            pid=self._process.pid if running and self._process else None,
            message=message,
        )
        self._last_info = info
        return info

    def build_command(self, info: QwenRuntimeInfo | None = None) -> list[str]:
        info = info or self.discover()
        if not info.executable:
            raise FileNotFoundError("Qwen executable was not found.")
        if not info.model:
            raise FileNotFoundError("Qwen GGUF model was not found.")

        if info.backend == "llama-server":
            cmd = [info.executable, "-m", info.model, "--host", self.host, "--port", str(self.port)]
        else:
            cmd = [
                info.executable,
                "-m",
                info.model,
                "--server",
                "--host",
                self.host,
                "--port",
                str(self.port),
            ]
        if self.extra_args:
            import shlex
            cmd.extend(shlex.split(self.extra_args, posix=False))
        return cmd

    def probe(self, timeout: float = 1.0) -> bool:
        # Fast socket check first so a stopped local runtime does not stall the UI.
        fast_timeout = max(0.05, min(float(timeout), 0.5))
        try:
            with socket.create_connection((self.host, self.port), timeout=fast_timeout):
                pass
        except OSError:
            return False
        for url in (f"http://{self.host}:{self.port}/health", f"http://{self.host}:{self.port}/v1/models"):
            try:
                response = httpx.get(url, timeout=max(0.2, float(timeout)))
                if response.status_code < 500:
                    return True
            except Exception:
                continue
        # Port is open even if an older backend lacks health/model endpoints.
        return True

    def start(self, wait_seconds: float = 15.0) -> QwenRuntimeInfo:
        with self._lock:
            if self.probe(timeout=0.5):
                info = self.discover()
                info.message = "Qwen server is already running"
                return info
            if self._process and self._process.poll() is None:
                return self.discover()

            info = self.discover()
            cmd = self.build_command(info)
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = LOG_DIR / "qwen_runtime.log"
            log_file = open(log_path, "a", encoding="utf-8", errors="replace")
            self._log_file = log_file
            creationflags = 0
            startupinfo = None
            if os.name == "nt":
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            logger.info("Starting Qwen runtime: %s", cmd)
            try:
                self._process = subprocess.Popen(
                    cmd,
                    cwd=info.folder or None,
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=creationflags,
                    startupinfo=startupinfo,
                    close_fds=(os.name != "nt"),
                )
            except Exception:
                log_file.close()
                self._log_file = None
                raise

        deadline = time.time() + max(0.5, wait_seconds)
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                break
            if self.probe(timeout=0.7):
                break
            time.sleep(0.35)
        result = self.discover()
        result.message = "Qwen server is ready" if result.reachable else "Qwen started but is not ready yet"
        return result

    def stop(self, wait_seconds: float = 1.0) -> QwenRuntimeInfo:
        with self._lock:
            process = self._process
            if process and process.poll() is None:
                try:
                    process.terminate()
                    process.wait(timeout=max(0.2, wait_seconds))
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                        process.wait(timeout=0.5)
                    except Exception:
                        pass
                except Exception:
                    logger.exception("Failed stopping Qwen process")
            self._process = None
            if self._log_file is not None:
                try:
                    self._log_file.close()
                except Exception:
                    pass
                self._log_file = None
        info = self.discover(probe=True)
        info.message = "Qwen stopped" if not info.reachable else "A Qwen server is still reachable on this port"
        return info

    def shutdown_quick(self) -> None:
        """Best-effort shutdown intended for application close; never waits long."""
        try:
            self.stop(wait_seconds=0.6)
        except Exception:
            logger.exception("Quick Qwen shutdown failed")

    def restart(self) -> QwenRuntimeInfo:
        self.stop()
        return self.start()

    def configure(
        self,
        *,
        folder: str | None = None,
        executable: str | None = None,
        model: str | None = None,
        host: str | None = None,
        port: int | None = None,
        extra_args: str | None = None,
    ) -> None:
        with self._lock:
            self.folder = Path(folder).expanduser() if str(folder or "").strip() else None
            self.executable_override = Path(executable).expanduser() if str(executable or "").strip() else None
            self.model_override = Path(model).expanduser() if str(model or "").strip() else None
            if host:
                self.host = host
            if port:
                self.port = int(port)
            if extra_args is not None:
                self.extra_args = str(extra_args).strip()
            self._asset_cache = None
            self._resolved_folder_cache = None


class QwenClient:
    """Minimal OpenAI-compatible local Qwen client for future AI features."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8080, timeout: float = 120.0) -> None:
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]], *, temperature: float = 0.1, max_tokens: int = 2048) -> str:
        payload = {
            "model": "local-qwen",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])

    def json_chat(self, messages: list[dict[str, str]], **kwargs) -> dict:
        text = self.chat(messages, **kwargs).strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text
            text = text.rsplit("```", 1)[0].strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
        return json.loads(text)
