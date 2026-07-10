"""HTTP client for the v5.0 Traffic Coordinator REST API.

Usage::

    from clients.traffic_coordinator_client import TrafficCoordinatorClient

    client = TrafficCoordinatorClient()
    health = client.health()
    client.ingest_state("mir", {"serialNumber": "mir-001", ...})
    result = client.submit_order(order_dict)
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

DEFAULT_COORDINATOR_URL = "http://traffic-coordinator:8000"
DEFAULT_TIMEOUT = 10  # seconds


@dataclass
class ClientResult:
    """Result of a coordinator API call."""

    ok: bool
    status: int | None = None
    data: dict | None = None
    error: str | None = None


class TrafficCoordinatorClient:
    """HTTP client for the v5.0 Traffic Coordinator."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = (base_url or os.getenv("TC_URL", DEFAULT_COORDINATOR_URL)).rstrip("/")
        self.api_key = api_key or os.getenv("TC_API_KEY", "")
        self.timeout = timeout

    # ── read endpoints ────────────────────────────────────────────

    def health(self) -> ClientResult:
        """GET /health — coordinator liveness check."""
        return self._get("/health", auth=False)

    def version(self) -> ClientResult:
        """GET /version — supported protocol versions."""
        return self._get("/version", auth=False)

    def state(self) -> ClientResult:
        """GET /state — platform state snapshot (requires auth)."""
        return self._get("/state")

    def metrics(self) -> ClientResult:
        """GET /metrics — in-memory metrics snapshot (requires auth)."""
        return self._get("/metrics")

    # ── write endpoints ───────────────────────────────────────────

    def ingest_state(self, brand: str, payload: dict) -> ClientResult:
        """POST /ingest/{brand} — submit a vendor-native robot state update."""
        return self._post(f"/ingest/{brand}", payload)

    def submit_order(self, order: dict) -> ClientResult:
        """POST /order — submit a WMS/ERP order.

        The *order* dict should contain at least ``order_id``, ``actions``,
        ``origin_lane``, ``destination_lane``, ``payload_kg``, and ``priority``.
        """
        return self._post("/order", order)

    def cancel_order(self, order_id: str) -> ClientResult:
        """POST /order/{order_id}/cancel — cancel a pending/active order."""
        return self._post(f"/order/{order_id}/cancel", {})

    # ── internal helpers ──────────────────────────────────────────

    def _get(self, path: str, auth: bool = True) -> ClientResult:
        return self._request("GET", path, body=None, auth=auth)

    def _post(self, path: str, body: dict | None, auth: bool = True) -> ClientResult:
        return self._request("POST", path, body=body, auth=auth)

    def _request(
        self, method: str, path: str, body: dict | None, auth: bool
    ) -> ClientResult:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if auth and self.api_key:
            headers["X-API-Key"] = self.api_key

        req = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                return ClientResult(
                    ok=True,
                    status=resp.status,
                    data=json.loads(raw) if raw else {},
                )
        except HTTPError as exc:
            try:
                body_text = exc.read().decode()
                error_data = json.loads(body_text)
            except Exception:
                error_data = None
            logger.warning(
                "coordinator HTTP %s %s → %s: %s",
                method, path, exc.code, error_data or exc.reason,
            )
            return ClientResult(
                ok=False,
                status=exc.code,
                error=str(error_data or exc.reason),
            )
        except URLError as exc:
            logger.warning("coordinator unreachable at %s: %s", url, exc.reason)
            return ClientResult(ok=False, error=f"unreachable: {exc.reason}")
        except (TimeoutError, OSError) as exc:
            logger.warning("coordinator timeout at %s: %s", url, exc)
            return ClientResult(ok=False, error=f"timeout: {exc}")
