"""
SAP EWM Warehouse Task Service — OData CRUD operations.

Handles:
- Fetching warehouse tasks from SAP EWM
- Creating/confirming/cancelling warehouse tasks
- CSRF token management with Redis caching
- Pagination (SAP returns max 100 records)
- Rate limiting (80 req/min)

References:
  REFERENCE/05_reference/sap/odata-warehouse-task-api.md
  REFERENCE/05_reference/sap/auth/csrf-token-flow.md
  REFERENCE/05_reference/sap/error-code-matrix.md
"""
import json
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx
import redis as rd

logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────

SAP_BASE_URL = os.getenv("SAP_BASE_URL", "http://sap-ewm:8000")
SAP_CLIENT = os.getenv("SAP_CLIENT", "100")
SAP_USER = os.getenv("SAP_USER", "")
SAP_PASSWORD_FILE = os.getenv("SAP_PASSWORD_FILE", "/run/secrets/sap_password")
SAP_AUTH = (SAP_USER, _read_password()) if SAP_USER else None
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# OData service root
ODATA_SERVICE = (
    "/sap/opu/odata4/sap/api_warehouse_order_task_2"
    "/srvd_a2x/sap/warehouseorder/0001"
)

# Rate limiting
MAX_REQUESTS_PER_MINUTE = 80
TOKEN_BUCKET_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE  # ~0.75s between requests

# CSRF token TTL
CSRF_REFRESH_INTERVAL = 1500  # 25 minutes (SAP tokens expire after ~30 min inactivity)


def _read_password() -> str:
    """Read SAP password from Docker Secrets file."""
    try:
        with open(SAP_PASSWORD_FILE) as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"SAP password file not found: {SAP_PASSWORD_FILE}")
        return os.getenv("SAP_PASSWORD", "")


# ── Data types ─────────────────────────────────────────

@dataclass
class WarehouseTask:
    """SAP EWM Warehouse Task."""
    warehouse: str
    task_id: str
    task_item: str
    warehouse_order: Optional[str] = None
    status: str = "0"  # 0=Open, 1=InProcess, 2=Confirmed, 3=Cancelled
    process_type: Optional[str] = None
    source_bin: Optional[str] = None
    dest_bin: Optional[str] = None
    product: Optional[str] = None
    batch: Optional[str] = None
    target_qty: Optional[float] = None
    actual_qty: Optional[float] = None
    is_hu_task: bool = False
    source_hu: Optional[str] = None
    dest_hu: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class InventoryItem:
    """Inventory snapshot from SAP EWM."""
    warehouse: str
    product: str
    batch: Optional[str] = None
    storage_bin: Optional[str] = None
    quantity: float = 0.0
    uom: str = "EA"
    storage_type: Optional[str] = None


# ── CSRF Token Manager ─────────────────────────────────

class CsrfTokenManager:
    """Manages SAP OData CSRF tokens with Redis caching."""

    def __init__(self, redis_client: rd.Redis):
        self._redis = redis_client

    def get_token(self) -> Optional[tuple[str, str]]:
        """Get cached CSRF token + cookies. Returns (token, cookie_str) or None."""
        token = self._redis.get("sap:csrf_token")
        cookies = self._redis.get("sap:csrf_cookies")
        if token and cookies:
            return token, cookies
        return None

    def set_token(self, token: str, cookies: str):
        """Cache CSRF token and cookies with TTL."""
        pipe = self._redis.pipeline()
        pipe.setex("sap:csrf_token", CSRF_REFRESH_INTERVAL, token)
        pipe.setex("sap:csrf_cookies", CSRF_REFRESH_INTERVAL, cookies)
        pipe.set("sap:csrf_last_refresh", str(time.time()))
        pipe.execute()

    def fetch_new(self, client: httpx.Client) -> tuple[str, str]:
        """Fetch a fresh CSRF token from SAP."""
        url = f"{SAP_BASE_URL}{ODATA_SERVICE}/$metadata"
        resp = client.get(
            url,
            headers={"X-CSRF-Token": "Fetch"},
            auth=SAP_AUTH,
        )
        resp.raise_for_status()
        token = resp.headers.get("X-CSRF-Token", "")
        if not token:
            raise RuntimeError("SAP did not return X-CSRF-Token header")

        # Extract cookies from response
        cookies = "; ".join(
            f"{c.name}={c.value}"
            for c in resp.cookies
        )
        self.set_token(token, cookies)
        logger.info("Fetched new CSRF token")
        return token, cookies


# ── Main Service ───────────────────────────────────────

class EwmWarehouseService:
    """SAP EWM OData warehouse task operations."""

    def __init__(self):
        self._redis = rd.from_url(REDIS_URL, decode_responses=True)
        self._csrf = CsrfTokenManager(self._redis)
        self._last_request_time = 0.0  # For rate limiting

    # ── Rate limiting ─────────────────────────────────

    def _throttle(self):
        """Ensure we don't exceed SAP rate limits (80 req/min)."""
        elapsed = time.time() - self._last_request_time
        if elapsed < TOKEN_BUCKET_INTERVAL:
            time.sleep(TOKEN_BUCKET_INTERVAL - elapsed)
        self._last_request_time = time.time()

    # ── HTTP client ───────────────────────────────────

    def _get_client(self) -> httpx.Client:
        return httpx.Client(timeout=30.0, verify=False)  # verify=False for internal SAP

    def _get_headers(self, csrf_token: Optional[str] = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-sap-client": SAP_CLIENT,
        }
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        return headers

    def _get_csrf_headers(self, client: httpx.Client) -> dict:
        """Get headers with valid CSRF token (fetch if needed)."""
        cached = self._csrf.get_token()
        if cached:
            token, cookies = cached
            return {
                **self._get_headers(token),
                "Cookie": cookies,
            }
        # Fetch new token
        token, cookies = self._csrf.fetch_new(client)
        return {
            **self._get_headers(token),
            "Cookie": cookies,
        }

    # ── Warehouse Task CRUD ──────────────────────────

    def list_tasks(
        self,
        warehouse: str = "WM01",
        status: str = "0",
        top: int = 100,
        skip: int = 0,
    ) -> list[WarehouseTask]:
        """Fetch open warehouse tasks from SAP EWM."""
        self._throttle()

        filter_str = f"EWMWarehouse eq '{warehouse}' and WarehouseTaskStatus eq '{status}'"
        params = {
            "$filter": filter_str,
            "$top": top,
            "$skip": skip,
        }

        with self._get_client() as client:
            url = f"{SAP_BASE_URL}{ODATA_SERVICE}/WarehouseTask"
            resp = client.get(
                url,
                params=params,
                headers=self._get_headers(),
                auth=SAP_AUTH,
            )

        if resp.status_code == 200:
            data = resp.json()
            return [self._parse_task(item) for item in data.get("d", {}).get("results", data.get("value", []))]
        elif resp.status_code == 401:
            logger.error("SAP auth failed — check credentials")
            raise PermissionError("SAP authentication failed")
        elif resp.status_code == 429:
            logger.warning("SAP rate limited — backing off")
            time.sleep(5)
            return self.list_tasks(warehouse, status, top, skip)
        else:
            logger.error(f"SAP error {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            return []

    def get_task(self, warehouse: str, task_id: str, task_item: str = "0001") -> Optional[WarehouseTask]:
        """Get a single warehouse task by ID."""
        self._throttle()
        key = f"EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',WarehouseTaskItem='{task_item}'"
        url = f"{SAP_BASE_URL}{ODATA_SERVICE}/WarehouseTask({key})"

        with self._get_client() as client:
            resp = client.get(url, headers=self._get_headers(), auth=SAP_AUTH)
            if resp.status_code == 200:
                return self._parse_task(resp.json().get("d", resp.json()))
            elif resp.status_code == 404:
                return None
            resp.raise_for_status()
            return None

    def create_task(self, task: WarehouseTask) -> Optional[WarehouseTask]:
        """Create a new warehouse task in SAP EWM."""
        self._throttle()

        payload = {
            "EWMWarehouse": task.warehouse,
            "WarehouseProcessType": task.process_type or "PICK",
            "SourceStorageBin": task.source_bin or "",
            "DestinationStorageBin": task.dest_bin or "",
            "ProductName": task.product or "",
            "TargetQuantityInBaseUnit": task.target_qty or 0,
            "BaseUnit": "EA",
            "Batch": task.batch or "",
        }

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            url = f"{SAP_BASE_URL}{ODATA_SERVICE}/WarehouseTask"
            resp = client.post(url, json=payload, headers=headers, auth=SAP_AUTH)

            if resp.status_code in (200, 201):
                logger.info(f"Created warehouse task for {task.product}")
                return self._parse_task(resp.json().get("d", resp.json()))
            elif resp.status_code == 403:
                # CSRF token expired — refresh and retry once
                logger.info("CSRF token expired, refreshing...")
                token, cookies = self._csrf.fetch_new(client)
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.post(url, json=payload, headers=headers, auth=SAP_AUTH)
                if resp.status_code in (200, 201):
                    return self._parse_task(resp.json().get("d", resp.json()))
            elif resp.status_code == 429:
                logger.warning("Rate limited on create, retrying after backoff")
                time.sleep(5)
                return self.create_task(task)

            logger.error(f"Create task failed: {resp.status_code} {resp.text[:200]}")
            return None

    def confirm_task(self, warehouse: str, task_id: str, qty: float,
                     task_item: str = "0001") -> bool:
        """Confirm a warehouse task (mark complete in SAP)."""
        self._throttle()
        key = f"EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',WarehouseTaskItem='{task_item}'"
        url = f"{SAP_BASE_URL}{ODATA_SERVICE}/WarehouseTask({key})/SAP__self.ConfirmWarehouseTaskExact"

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            resp = client.post(url, json={}, headers=headers, auth=SAP_AUTH)

            if resp.status_code == 200:
                logger.info(f"Confirmed task {task_id}")
                return True
            elif resp.status_code == 403:
                token, cookies = self._csrf.fetch_new(client)
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.post(url, json={}, headers=headers, auth=SAP_AUTH)
                return resp.status_code == 200

            logger.error(f"Confirm task {task_id} failed: {resp.status_code}")
            return False

    def cancel_task(self, warehouse: str, task_id: str, task_item: str = "0001") -> bool:
        """Cancel a warehouse task."""
        self._throttle()
        key = f"EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',WarehouseTaskItem='{task_item}'"
        url = f"{SAP_BASE_URL}{ODATA_SERVICE}/WarehouseTask({key})/SAP__self.CancelWarehouseTask"

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            resp = client.post(url, json={}, headers=headers, auth=SAP_AUTH)

            if resp.status_code == 200:
                logger.info(f"Cancelled task {task_id}")
                return True
            elif resp.status_code == 403:
                token, cookies = self._csrf.fetch_new(client)
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.post(url, json={}, headers=headers, auth=SAP_AUTH)
                return resp.status_code == 200

            logger.error(f"Cancel task {task_id} failed: {resp.status_code}")
            return False

    # ── Parsing ─────────────────────────────────────

    @staticmethod
    def _parse_task(item: dict) -> WarehouseTask:
        return WarehouseTask(
            warehouse=item.get("EWMWarehouse", ""),
            task_id=item.get("WarehouseTask", ""),
            task_item=item.get("WarehouseTaskItem", "0001"),
            warehouse_order=item.get("WarehouseOrder"),
            status=item.get("WarehouseTaskStatus", "0"),
            process_type=item.get("WarehouseProcessType"),
            source_bin=item.get("SourceStorageBin"),
            dest_bin=item.get("DestinationStorageBin"),
            product=item.get("ProductName"),
            batch=item.get("Batch"),
            target_qty=float(item.get("TargetQuantityInBaseUnit", 0) or 0),
            actual_qty=float(item.get("ActualQuantityInBaseUnit", 0) or 0),
            is_hu_task=bool(item.get("IsHandlingUnitWarehouseTask", False)),
            source_hu=item.get("SourceHandlingUnit"),
            dest_hu=item.get("DestinationHandlingUnit"),
            raw=item,
        )

    # ── Health ───────────────────────────────────────

    def check_connection(self) -> dict:
        """Test SAP connectivity and return status."""
        try:
            with self._get_client() as client:
                url = f"{SAP_BASE_URL}{ODATA_SERVICE}/$metadata"
                resp = client.get(url, headers=self._get_headers(), auth=SAP_AUTH, timeout=10)
                return {
                    "connected": resp.status_code == 200,
                    "status_code": resp.status_code,
                    "auth_configured": SAP_AUTH is not None,
                }
        except Exception as e:
            return {"connected": False, "error": str(e)}
