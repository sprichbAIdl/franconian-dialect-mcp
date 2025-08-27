#!/usr/bin/env python3
"""
Minimalist HTTP client for BDO API access.
Does ONLY HTTP - no business logic contamination.
"""

from __future__ import annotations

import httpx

from .domain import APIError


# Minimalist HTTP client - does ONLY HTTP
class MinimalistHTTPClient:
    """Minimalist HTTP client - constrained to essential functionality."""
    
    def __init__(self, timeout: float = 30.0) -> None:
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout
    
    async def get_raw_response(self, url: str, params: dict[str, str]) -> str:
        """Get raw HTTP response - nothing more."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        
        try:
            response = await self._client.get(url, params=params)
            response.raise_for_status()
            return response.text
        except httpx.HTTPError as e:
            raise APIError(f"HTTP request failed: {e}") from e
    
    async def close(self) -> None:
        """Close client resources."""
        if self._client:
            await self._client.aclose()
            self._client = None