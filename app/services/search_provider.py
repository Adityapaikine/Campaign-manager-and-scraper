from __future__ import annotations

import os
import time
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx
from request_limits import REQUEST_LIMITS, RequestDeferred
from scraper_engine import lookup_budget
from dotenv import load_dotenv

from app.utils.config import ENV_CANDIDATES

for _env_path in ENV_CANDIDATES:
    if _env_path.exists():
        load_dotenv(_env_path, override=False)


class SearchProviderError(RuntimeError):
    """Raised when a configured search provider cannot complete a request."""


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    provider: str = ""


class SearchProvider(ABC):
    """Phase-5 web-search abstraction.

    Implementations return only ordinary search metadata (title, URL, snippet).
    Pattern discovery is deliberately kept outside provider classes so a provider
    can be swapped without changing business logic.
    """

    name = "Base"

    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        retries: int = 2,
        backoff_seconds: float = 0.75,
        min_request_interval_seconds: float = 1.0,
    ) -> None:
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.retries = max(0, int(retries))
        self.backoff_seconds = max(0.05, float(backoff_seconds))
        self.min_request_interval_seconds = max(0.0, float(min_request_interval_seconds))
        self._last_request_at = 0.0
        self._rate_lock = threading.Lock()
        self._clients = []
        self._local = threading.local()
        self.control = None
        self.metrics = None

    def close(self):
        for client in self._clients:
            client.close()
        self._clients.clear()

    def _client(self):
        client = getattr(self._local, "client", None)
        if client is None:
            client = httpx.Client(follow_redirects=True, headers={"User-Agent": "B2B-Lead-Workspace"})
            self._local.client = client
            with self._rate_lock:
                self._clients.append(client)
        return client

    @property
    def configured(self) -> bool:
        return True

    def _wait_for_rate_limit(self) -> None:
        if self.min_request_interval_seconds <= 0:
            return
        with self._rate_lock:
            elapsed = time.monotonic() - self._last_request_at
            wait_for = self.min_request_interval_seconds - elapsed
            if wait_for > 0:
                lookup_budget.sleep(wait_for)
            # Reserve this request slot before releasing the lock so concurrent
            # domain workers cannot all pass the limiter at the same instant.
            self._last_request_at = time.monotonic()

    def _request_json(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            lookup_budget.timeout(1)
            try:
                with REQUEST_LIMITS.slot(url, interval=self.min_request_interval_seconds, concurrency=2,
                        budget=lookup_budget, checkpoint=self.control.checkpoint if self.control else None,
                        metrics=self.metrics):
                    response = self._client().request(method, url, timeout=lookup_budget.timeout(self.timeout_seconds) / 4, **kwargs)
                if response.status_code == 429 or response.status_code >= 500:
                    if response.status_code in {429, 503}:
                        REQUEST_LIMITS.cooldown(url, response.headers.get("Retry-After"))
                    raise SearchProviderError(
                        f"{self.name} returned HTTP {response.status_code}."
                    )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise SearchProviderError(f"{self.name} returned an unexpected response.")
                return payload
            except RequestDeferred as exc:
                raise SearchProviderError(str(exc)) from exc
            except (httpx.HTTPError, ValueError, SearchProviderError) as exc:
                last_exc = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {401, 403}:
                    break
                if attempt >= self.retries:
                    break
                lookup_budget.sleep(self.backoff_seconds * (2**attempt))
        raise SearchProviderError(f"{self.name} search failed: {last_exc}")

    @abstractmethod
    def search(self, query: str, *, count: int = 10) -> list[SearchResult]:
        raise NotImplementedError


class DisabledSearchProvider(SearchProvider):
    name = "Disabled"

    @property
    def configured(self) -> bool:
        return False

    def search(self, query: str, *, count: int = 10) -> list[SearchResult]:
        return []


class BraveSearchProvider(SearchProvider):
    name = "Brave"

    def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = (api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, count: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("BRAVE_SEARCH_API_KEY is not configured.")
        payload = self._request_json(
            "GET",
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            params={"q": query, "count": max(1, min(int(count), 20)), "search_lang": "en"},
        )
        results = payload.get("web", {}).get("results", [])
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("description", "")),
                provider=self.name,
            )
            for item in results
            if isinstance(item, dict)
        ]


class SerperSearchProvider(SearchProvider):
    name = "Serper"

    def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = (api_key or os.getenv("SERPER_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, count: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("SERPER_API_KEY is not configured.")
        payload = self._request_json(
            "POST",
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max(1, min(int(count), 20))},
        )
        results = payload.get("organic", [])
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("link", "")),
                snippet=str(item.get("snippet", "")),
                provider=self.name,
            )
            for item in results
            if isinstance(item, dict)
        ]


class SerpApiSearchProvider(SearchProvider):
    name = "SerpAPI"

    def __init__(self, *, api_key: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.api_key = (api_key or os.getenv("SERPAPI_API_KEY", "")).strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def search(self, query: str, *, count: int = 10) -> list[SearchResult]:
        if not self.configured:
            raise SearchProviderError("SERPAPI_API_KEY is not configured.")
        payload = self._request_json(
            "GET",
            "https://serpapi.com/search",
            params={
                "engine": "google",
                "q": query,
                "api_key": self.api_key,
                "num": max(1, min(int(count), 20)),
            },
        )
        results = payload.get("organic_results", [])
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("link", "")),
                snippet=str(item.get("snippet", "")),
                provider=self.name,
            )
            for item in results
            if isinstance(item, dict)
        ]


def configured_provider_names() -> list[str]:
    names = ["Disabled"]
    if os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        names.append("Brave")
    if os.getenv("SERPER_API_KEY", "").strip():
        names.append("Serper")
    if os.getenv("SERPAPI_API_KEY", "").strip():
        names.append("SerpAPI")
    return names


def create_search_provider(
    name: str = "Auto",
    *,
    timeout_seconds: float = 15.0,
    retries: int = 2,
    min_request_interval_seconds: float = 0.25,
) -> SearchProvider:
    kwargs = {
        "timeout_seconds": timeout_seconds,
        "retries": retries,
        "min_request_interval_seconds": min_request_interval_seconds,
    }
    normalized = (name or "Auto").strip().casefold()
    if normalized in {"disabled", "none", "off"}:
        return DisabledSearchProvider(**kwargs)
    if normalized == "brave":
        return BraveSearchProvider(**kwargs)
    if normalized == "serper":
        return SerperSearchProvider(**kwargs)
    if normalized in {"serpapi", "serp api"}:
        return SerpApiSearchProvider(**kwargs)

    # Auto: prefer Brave, then Serper, then SerpAPI, based on configured keys.
    for provider_cls in (BraveSearchProvider, SerperSearchProvider, SerpApiSearchProvider):
        provider = provider_cls(**kwargs)
        if provider.configured:
            return provider
    return DisabledSearchProvider(**kwargs)
