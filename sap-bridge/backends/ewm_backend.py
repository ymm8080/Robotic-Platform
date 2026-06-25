"""SAP EWM backend — OData V4 warehouse task operations.

Extracted from services/ewm_warehouse_service.py into the WarehouseBackend ABC.
Supports both V2 and V4 OData protocols with CSRF token management, rate limiting,
and pagination.

References:
  REFERENCE/05_reference/sap/odata-warehouse-task-api.md
  REFERENCE/05_reference/sap/auth/csrf-token-flow.md
  REFERENCE/05_reference/sap/error-code-matrix.md
"""

import logging
import os
import re
import time

import httpx
import redis as rd

from models.warehouse_task import WarehouseTask

from .base import WarehouseBackend

logger = logging.getLogger(__name__)

# ── Defaults ───────────────────────────────────────────────

DEFAULT_BASE_URL = os.getenv("SAP_BASE_URL", "http://sap-ewm:8000")
DEFAULT_CLIENT = os.getenv("SAP_CLIENT", "100")
DEFAULT_USER = os.getenv("SAP_USER", "")
DEFAULT_PASSWORD_FILE = os.getenv("SAP_PASSWORD_FILE", "/run/secrets/sap_password")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

ODATA_SERVICE = (
    "/sap/opu/odata4/sap/api_warehouse_order_task_2"
    "/srvd_a2x/sap/warehouseorder/0001"
)

MAX_REQUESTS_PER_MINUTE = 80
TOKEN_BUCKET_INTERVAL = 60.0 / MAX_REQUESTS_PER_MINUTE
CSRF_REFRESH_INTERVAL = 1500  # 25 minutes


def _read_password(password_file: str) -> str:
    try:
        with open(password_file) as f:
            return f.read().strip()
    except FileNotFoundError:
        logger.warning(f"SAP password file not found: {password_file}")
        return os.getenv("SAP_PASSWORD", "")


# ── CSRF Token Manager ─────────────────────────────────────

class CsrfTokenManager:
    """Manages SAP OData CSRF tokens with Redis caching."""

    def __init__(self, redis_client: rd.Redis, auth: tuple[str, str] | None = None):
        self._redis = redis_client
        self._auth = auth

    def get_token(self) -> tuple[str, str] | None:
        token = self._redis.get("sap:csrf_token")
        cookies = self._redis.get("sap:csrf_cookies")
        if token and cookies:
            return (token, cookies)
        return None

    def set_token(self, token: str, cookies: str):
        pipe = self._redis.pipeline()
        pipe.setex("sap:csrf_token", CSRF_REFRESH_INTERVAL, token)
        pipe.setex("sap:csrf_cookies", CSRF_REFRESH_INTERVAL, cookies)
        pipe.set("sap:csrf_last_refresh", str(time.time()))
        pipe.execute()

    def fetch_new(self, client: httpx.Client, base_url: str, odata_service: str) -> tuple[str, str]:
        url = f"{base_url}{odata_service}/$metadata"
        resp = client.get(
            url, headers={"X-CSRF-Token": "Fetch"}, auth=self._auth,
        )
        resp.raise_for_status()
        token = resp.headers.get("X-CSRF-Token", "")
        if not token:
            raise RuntimeError("SAP did not return X-CSRF-Token header")
        cookies = "; ".join(f"{c.name}={c.value}" for c in resp.cookies)
        self.set_token(token, cookies)
        logger.info("Fetched new CSRF token")
        return token, cookies

    def close(self):
        """Close Redis connection."""
        try:
            self._redis.close()
        except Exception:
            pass


# ── EWM Backend ────────────────────────────────────────────

class EwmBackend(WarehouseBackend):
    """SAP EWM OData warehouse task operations."""

    # Class-level identifiers (used by Registry — no __init__ needed to inspect)
    backend_type_name = "ewm"
    display_name_str = "SAP EWM"

    def __init__(self, config: dict | None = None):
        self._cfg = config or {}
        self._base_url = self._cfg.get("base_url", DEFAULT_BASE_URL)
        self._client = self._cfg.get("client", DEFAULT_CLIENT)
        self._odata_service = self._cfg.get("odata_service", ODATA_SERVICE)
        self._rate_limit = int(self._cfg.get("rate_limit", MAX_REQUESTS_PER_MINUTE))
        self._token_interval = 60.0 / self._rate_limit

        user = self._cfg.get("user", DEFAULT_USER)
        pw_file = self._cfg.get("password_file", DEFAULT_PASSWORD_FILE)
        password = self._cfg.get("password") or _read_password(pw_file)
        self._auth = (user, password) if user else None

        # Lazy init — Redis connection created on first use
        self._redis: rd.Redis | None = None
        self._csrf: CsrfTokenManager | None = None
        self._last_request_time = 0.0

    def _ensure_redis(self) -> rd.Redis:
        """Get or create Redis connection (lazy init)."""
        if self._redis is None:
            self._redis = rd.from_url(self._cfg.get("redis_url", REDIS_URL), decode_responses=True)
        return self._redis

    def _ensure_csrf(self) -> CsrfTokenManager:
        """Get or create CSRF token manager (lazy init)."""
        if self._csrf is None:
            self._csrf = CsrfTokenManager(self._ensure_redis(), auth=self._auth)
        return self._csrf

    # ── Rate limiting ────────────────────────────────────

    def _throttle(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self._token_interval:
            time.sleep(self._token_interval - elapsed)
        self._last_request_time = time.time()

    # ── HTTP helpers ─────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        verify_ssl = os.getenv("SAP_VERIFY_SSL", "false").lower() == "true"
        return httpx.Client(timeout=30.0, verify=verify_ssl)

    def _get_headers(self, csrf_token: str | None = None) -> dict:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "x-sap-client": self._client,
        }
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        return headers

    def _get_csrf_headers(self, client: httpx.Client) -> dict:
        csrf = self._ensure_csrf()
        cached = csrf.get_token()
        if cached:
            token, cookies = cached
            return {**self._get_headers(token), "Cookie": cookies}
        token, cookies = csrf.fetch_new(client, self._base_url, self._odata_service)
        return {**self._get_headers(token), "Cookie": cookies}

    # ── Task CRUD ────────────────────────────────────────

    def list_tasks(self, warehouse: str = "WM01", status: str = "0",
                   top: int = 100, skip: int = 0) -> list[WarehouseTask]:
        self._throttle()
        if not re.match(r'^[A-Za-z0-9_\-]+$', warehouse):
            logger.error(f"Invalid warehouse param: {warehouse!r}")
            return []
        if not re.match(r'^[A-Za-z0-9_\-]+$', status):
            logger.error(f"Invalid status param: {status!r}")
            return []
        filter_str = f"EWMWarehouse eq '{warehouse}' and WarehouseTaskStatus eq '{status}'"
        params = {"$filter": filter_str, "$top": top, "$skip": skip}

        with self._get_client() as client:
            url = f"{self._base_url}{self._odata_service}/WarehouseTask"
            resp = client.get(url, params=params, headers=self._get_headers(), auth=self._auth)

        if resp.status_code == 200:
            data = resp.json()
            raw_list = data.get("d", {}).get("results", data.get("value", []))
            return [self._parse_task(item) for item in raw_list]
        elif resp.status_code == 401:
            logger.error("SAP auth failed — check credentials")
            raise PermissionError("SAP authentication failed")
        elif resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2))
            delay = min(retry_after, 30)
            logger.warning(f"SAP rate limited — backing off {delay}s")
            time.sleep(delay)
            return self.list_tasks(warehouse, status, top, skip)
        else:
            logger.error(f"SAP error {resp.status_code}: {resp.text[:200]}")
            resp.raise_for_status()
            return []

    def get_task(self, warehouse: str, task_id: str, item_no: str = "0001") -> WarehouseTask | None:
        self._throttle()
        key = f"EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',WarehouseTaskItem='{item_no}'"
        url = f"{self._base_url}{self._odata_service}/WarehouseTask({key})"

        with self._get_client() as client:
            resp = client.get(url, headers=self._get_headers(), auth=self._auth)
            if resp.status_code == 200:
                return self._parse_task(resp.json().get("d", resp.json()))
            elif resp.status_code == 404:
                return None
            resp.raise_for_status()
            return None

    def create_task(self, task: WarehouseTask) -> WarehouseTask | None:
        self._throttle()
        payload = {
            "EWMWarehouse": task.warehouse,
            "WarehouseProcessType": task.process_type or "PICK",
            "SourceStorageBin": task.source_bin or "",
            "DestinationStorageBin": task.dest_bin or "",
            "ProductName": task.product or "",
            "TargetQuantityInBaseUnit": task.target_qty or 0,
            "BaseUnit": task.uom or "EA",
            "Batch": task.batch or "",
        }

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            url = f"{self._base_url}{self._odata_service}/WarehouseTask"
            resp = client.post(url, json=payload, headers=headers, auth=self._auth)

            if resp.status_code in (200, 201):
                logger.info(f"Created warehouse task for {task.product}")
                return self._parse_task(resp.json().get("d", resp.json()))
            elif resp.status_code == 403:
                logger.info("CSRF token expired, refreshing...")
                csrf = self._ensure_csrf()
                token, cookies = csrf.fetch_new(client, self._base_url, self._odata_service)
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.post(url, json=payload, headers=headers, auth=self._auth)
                if resp.status_code in (200, 201):
                    return self._parse_task(resp.json().get("d", resp.json()))
            elif resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 2))
                delay = min(retry_after, 30)
                logger.warning(f"Rate limited on create, retrying after {delay}s backoff")
                time.sleep(delay)
                return self.create_task(task)

            logger.error(f"Create task failed: {resp.status_code} {resp.text[:200]}")
            return None

    def confirm_task(self, warehouse: str, task_id: str, qty: float,
                     item_no: str = "0001") -> bool:
        self._throttle()
        key = (f"EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',"
               f"WarehouseTaskItem='{item_no}'")
        url = f"{self._base_url}{self._odata_service}/WarehouseTask({key})/SAP__self.ConfirmWarehouseTaskExact"

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            resp = client.post(url, json={}, headers=headers, auth=self._auth)
            if resp.status_code == 200:
                logger.info(f"Confirmed task {task_id}")
                return True
            elif resp.status_code == 403:
                csrf = self._ensure_csrf()
                token, cookies = csrf.fetch_new(client, self._base_url, self._odata_service)
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.post(url, json={}, headers=headers, auth=self._auth)
                return resp.status_code == 200
            logger.error(f"Confirm task {task_id} failed: {resp.status_code}")
            return False

    def cancel_task(self, warehouse: str, task_id: str, item_no: str = "0001") -> bool:
        self._throttle()
        key = (f"EWMWarehouse='{warehouse}',WarehouseTask='{task_id}',"
               f"WarehouseTaskItem='{item_no}'")
        url = f"{self._base_url}{self._odata_service}/WarehouseTask({key})/SAP__self.CancelWarehouseTask"

        with self._get_client() as client:
            headers = self._get_csrf_headers(client)
            resp = client.post(url, json={}, headers=headers, auth=self._auth)
            if resp.status_code == 200:
                logger.info(f"Cancelled task {task_id}")
                return True
            elif resp.status_code == 403:
                csrf = self._ensure_csrf()
                token, cookies = csrf.fetch_new(client, self._base_url, self._odata_service)
                headers["X-CSRF-Token"] = token
                headers["Cookie"] = cookies
                resp = client.post(url, json={}, headers=headers, auth=self._auth)
                return resp.status_code == 200
            logger.error(f"Cancel task {task_id} failed: {resp.status_code}")
            return False

    # ── Health ───────────────────────────────────────────

    def check_connection(self) -> dict:
        try:
            with self._get_client() as client:
                url = f"{self._base_url}{self._odata_service}/$metadata"
                resp = client.get(url, headers=self._get_headers(), auth=self._auth, timeout=10)
                return {
                    "connected": resp.status_code == 200,
                    "backend": self.backend_type,
                    "mode": "odata",
                    "warehouse_configured": self._auth is not None,
                    "details": {"status_code": resp.status_code},
                }
        except Exception as e:
            return {
                "connected": False,
                "backend": self.backend_type,
                "mode": "odata",
                "warehouse_configured": self._auth is not None,
                "error": str(e)[:200],
            }

    # ── Lifecycle ────────────────────────────────────────

    def close(self):
        """Release Redis and httpx connections."""
        if self._csrf is not None:
            try:
                self._csrf.close()
            except Exception:
                pass
            self._csrf = None
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None
        logger.debug("EwmBackend connections closed")

    # ── Parsing ──────────────────────────────────────────

    def _parse_task(self, item: dict) -> WarehouseTask:
        ewm_status = item.get("WarehouseTaskStatus", "0")
        return WarehouseTask(
            source_system="EWM",
            warehouse=item.get("EWMWarehouse", ""),
            external_id=item.get("WarehouseTask", ""),
            item_no=item.get("WarehouseTaskItem", "0001"),
            task_type=self._map_process_type(item.get("WarehouseProcessType")),
            source_bin=item.get("SourceStorageBin"),
            dest_bin=item.get("DestinationStorageBin"),
            product=item.get("ProductName"),
            batch=item.get("Batch"),
            target_qty=float(item.get("TargetQuantityInBaseUnit", 0) or 0),
            actual_qty=float(item.get("ActualQuantityInBaseUnit", 0) or 0),
            uom=item.get("BaseUnit", "EA"),
            status=ewm_status,
            vendor_data={
                "warehouse_order": item.get("WarehouseOrder"),
                "process_type": item.get("WarehouseProcessType"),
                "is_hu_task": bool(item.get("IsHandlingUnitWarehouseTask", False)),
                "source_hu": item.get("SourceHandlingUnit"),
                "dest_hu": item.get("DestinationHandlingUnit"),
                "raw": item,
            },
        )

    @staticmethod
    def _map_process_type(pt: str | None) -> str:
        if not pt:
            return "MOVE"
        pt_upper = pt.upper()
        if "PICK" in pt_upper or "PIK" in pt_upper:
            return "PICK"
        if "PUT" in pt_upper or "STO" in pt_upper:
            return "PUT"
        if "CHA" in pt_upper or "CHG" in pt_upper:
            return "CHARGE"
        return "MOVE"

    def validate_config(self) -> list[str]:
        errors = []
        if not self._auth or not self._auth[0]:
            errors.append("SAP EWM user not configured")
        if not self._base_url or self._base_url == DEFAULT_BASE_URL:
            errors.append("SAP EWM base_url may be default — check config")
        return errors
