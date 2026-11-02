from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

import httpx

from .config import get_settings
from .errors import BackendApiError, BackendInvalidResponseError, BackendTimeoutError, BackendUnavailableError


class PetHospitalRestClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or get_settings().pet_hospital_base_url).rstrip("/")
        self.timeout = get_settings().request_timeout

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        last_exc: Exception | None = None
        for attempt in range(get_settings().max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.get(url, params=params)
                if response.status_code >= 400:
                    raise BackendApiError(response.status_code, f"Backend returned {response.status_code}", {"path": path})
                try:
                    payload = response.json()
                except ValueError as exc:
                    raise BackendInvalidResponseError("Backend returned invalid JSON") from exc
                if not isinstance(payload, dict):
                    raise BackendInvalidResponseError("Backend response is not an object")
                return payload
            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                last_exc = exc
                if attempt < get_settings().max_retries:
                    continue
                raise BackendTimeoutError("Request to backend timed out") from exc
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < get_settings().max_retries:
                    continue
                raise BackendUnavailableError("Could not reach backend") from exc
            except BackendApiError:
                raise
            except BackendInvalidResponseError:
                raise
        if last_exc is not None:
            raise BackendUnavailableError("Backend request failed", {"reason": str(last_exc)})
        raise BackendUnavailableError("Backend request failed")
