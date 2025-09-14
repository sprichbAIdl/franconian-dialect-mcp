#!/usr/bin/env python3
"""
HTTP client for BDO API access.
"""

from __future__ import annotations

import asyncio
import time
import httpx

from .domain import APIError


class MinimalistHTTPClient:
    def __init__(self, timeout: float = 30.0, rate_limit_seconds: float = 1.0) -> None:
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
        self._rate_limit_seconds = rate_limit_seconds
        self._last_request_time: float = 0.0
        self._rate_limit_lock = asyncio.Lock()

    async def get_raw_response(self, url: str, params: dict[str, str]) -> str:
        await self._enforce_rate_limit()

        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            raise APIError(f"HTTP request failed: {e}") from e

    async def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting by ensuring minimum time between requests."""
        async with self._rate_limit_lock:
            current_time = time.time()
            time_since_last_request = current_time - self._last_request_time

            if time_since_last_request < self._rate_limit_seconds:
                sleep_duration = self._rate_limit_seconds - time_since_last_request
                await asyncio.sleep(sleep_duration)

            self._last_request_time = time.time()

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
