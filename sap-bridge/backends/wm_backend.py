"""SAP Classic WM (LE-WM) backend — RFC/BAPI integration via pyrfc or HTTP.

Dual-mode:
  mode: rfc   (default) — Real SAP WM via pyrfc (SAP NW RFC SDK required)
  mode: http           — WM RFC Simulator over HTTP (for dev/test)

References:
  REFERENCE/05_reference/sap/wm-classic-integration.md
  REFERENCE/05_reference/sap/rfc-function-module-catalog.md
  REFERENCE/05_reference/sap/error-code-matrix.md
"""

import contextlib
import logging
import os
import time

from models.warehouse_task import WarehouseTask

from .base import WarehouseBackend

logger = logging.getLogger(__name__)

# ── Configuration defaults ─────────────────────────────────

DEFAULT_RFC_HOST = os.getenv("SAP_ASHOST", "")
DEFAULT_RFC_SYSNR = os.getenv("SAP_SYSNR", "00")
DEFAULT_RFC_CLIENT = os.getenv("SAP_CLIENT", "100")
DEFAULT_RFC_USER = os.getenv("SAP_USER", "")
DEFAULT_RFC_PASSWORD_FILE = os.getenv("SAP_PASSWORD_FILE", "/run/secrets/sap_password")
DEFAULT_RFC_LANG = os.getenv("SAP_LANG", "ZH")
DEFAULT_WM_SIMULATOR_URL = os.getenv("WM_SIMULATOR_URL", "http://wm-simulator:8001")

# Retry settings
RFC_MAX_RETRIES = 3
RFC_RETRY_DELAYS = [1.0, 2.0, 4.0]

# Movement type → task type mapping
MOVEMENT_TYPE_MAP = {
    "999": "MOVE",
    "101": "PUT",     # Goods receipt
    "102": "PUT",     # GR reversal
    "201": "PICK",    # Goods issue (production)
    "202": "PICK",    # GI reversal
    "301": "MOVE",    # Transfer posting
    "321": "PUT",     # Putaway
    "322": "PICK",    # Removal
}

# Transfer type → task type
TRANSFER_TYPE_MAP = {
    "E": "PUT",       # Einlagerung (putaway)
    "A": "PICK",      # Auslagerung (removal)
    "U": "MOVE",      # Umlagerung (transfer)
}


class WmBackend(WarehouseBackend):
    """SAP Classic WM (LE-WM) backend.

    Two modes:
      - mode='rfc' (default): Real SAP WM via pyrfc
      - mode='http': WM RFC Simulator over HTTP
    """

    # Class-level identifiers (used by Registry — no __init__ needed)
    backend_type_name = "wm"
    display_name_str = "SAP Classic WM (LE-WM)"

    def __init__(self, config: dict | None = None):
        self._cfg = config or {}
        self._mode = self._cfg.get("mode", "rfc").lower()

        self._http_client: "httpx.Client | None" = None
        self._last_conn = None
        self._last_conn_time = 0.0
        self._conn_ttl = 300  # Reconnect every 5 min

        if self._mode == "http":
            self._simulator_url = self._cfg.get(
                "simulator_url", DEFAULT_WM_SIMULATOR_URL
            )
            self.display_name_str = f"SAP WM via Simulator ({self._simulator_url})"
        else:
            self._conn_params = self._build_conn_params()

    def _build_conn_params(self) -> dict:
        pw_file = self._cfg.get("password_file", DEFAULT_RFC_PASSWORD_FILE)
        password = self._cfg.get("password")
        if not password:
            try:
                with open(pw_file) as f:
                    password = f.read().strip()
            except FileNotFoundError:
                password = os.getenv("SAP_PASSWORD", "")

        return {
            "ashost": self._cfg.get("rfc_ashost", DEFAULT_RFC_HOST),
            "sysnr": self._cfg.get("rfc_sysnr", DEFAULT_RFC_SYSNR),
            "client": self._cfg.get("rfc_client", DEFAULT_RFC_CLIENT),
            "user": self._cfg.get("rfc_user", DEFAULT_RFC_USER),
            "passwd": password,
            "lang": self._cfg.get("rfc_lang", DEFAULT_RFC_LANG),
        }

    # ── WarehouseBackend ABC ─────────────────────────────

    @property
    def backend_type(self) -> str:
        return "wm"

    @property
    def display_name(self) -> str:
        return self.display_name_str

    # ── Connection (RFC mode) ────────────────────────────

    def _get_connection(self):
        now = time.time()
        if self._last_conn is None or (now - self._last_conn_time) > self._conn_ttl:
            self._close_rfc_connection()
            self._last_conn = self._create_connection()
            self._last_conn_time = now
        return self._last_conn

    def _create_connection(self):
        try:
            import pyrfc
            conn = pyrfc.Connection(**self._conn_params)
            logger.info("WM RFC connection established")
            return conn
        except ImportError:
            logger.error(
                "pyrfc not installed. Install with: pip install pyrfc\n"
                "Requires SAP NW RFC SDK DLLs."
            )
            raise
        except Exception as e:
            logger.error(f"WM RFC connection failed: {e}")
            raise

    def _close_rfc_connection(self):
        if self._last_conn is not None:
            with contextlib.suppress(Exception):
                self._last_conn.close()
            self._last_conn = None

    # ── HTTP client (simulator mode) ─────────────────────

    def _get_http_client(self):
        if self._http_client is None:
            import httpx
            self._http_client = httpx.Client(base_url=self._simulator_url, timeout=30.0)
        return self._http_client

    def _call_http(self, func_name: str, **params) -> dict:
        """Call an RFC function via HTTP simulator."""
        client = self._get_http_client()
        resp = client.post(f"/rfc/{func_name}", json=params)
        resp.raise_for_status()
        return resp.json()

    # ── Unified RFC call ─────────────────────────────────

    def _call_rfc(self, func_name: str, **params) -> dict:
        """Dispatch to RFC or HTTP based on mode."""
        if self._mode == "http":
            return self._call_http(func_name, **params)

        # RFC mode with retry
        last_error = None
        for attempt, delay in enumerate(RFC_RETRY_DELAYS):
            try:
                conn = self._get_connection()
                result = conn.call(func_name, **params)
                return result
            except Exception as e:
                last_error = e
                error_str = str(e)
                logger.warning(f"RFC {func_name} attempt {attempt + 1} failed: {error_str[:100]}")

                if "not authorized" in error_str.lower() or "permission" in error_str.lower():
                    logger.error(f"WM RFC authorization error on {func_name}")
                    raise

                self._close_rfc_connection()

                if attempt < len(RFC_RETRY_DELAYS) - 1:
                    time.sleep(delay)

        logger.error(f"RFC {func_name} failed after {RFC_MAX_RETRIES} attempts: {last_error}")
        raise RuntimeError(f"RFC {func_name} failed: {last_error}") from last_error

    # ── Task CRUD ────────────────────────────────────────

    def list_tasks(self, warehouse: str = "001", status: str = "0",
                   top: int = 100, skip: int = 0) -> list[WarehouseTask]:
        try:
            result = self._call_rfc("L_TO_READ", I_LGNUM=warehouse)
        except Exception as e:
            logger.error(f"Failed to list WM tasks for {warehouse}: {e}")
            return []

        tasks = []
        headers = self._extract_table(result, "T_HEADERS", [])
        for hdr in headers:
            tanum = str(hdr.get("TANUM", ""))
            raw_status = str(hdr.get("STATUS", "0"))

            if status and raw_status != status:
                continue

            items = self._get_to_items(warehouse, tanum)
            if items:
                for item in items:
                    tasks.append(self._parse_to(item, warehouse))
            else:
                tasks.append(self._parse_to(hdr, warehouse))

            if len(tasks) >= top:
                break

        return tasks[skip:skip + top]

    def get_task(self, warehouse: str, task_id: str, item_no: str = "0001") -> WarehouseTask | None:
        try:
            result = self._call_rfc("L_TO_READ", I_LGNUM=warehouse, I_TANUM=task_id)
            items = self._extract_table(result, "T_HEADERS", [])
            if not items:
                return None

            hdr = items[0]
            item_rows = self._extract_table(result, "T_ITEMS", [])
            target_item = next((i for i in item_rows if str(i.get("TAPOS", "")) == item_no), None)
            return self._parse_to(target_item or hdr, warehouse)
        except Exception as e:
            logger.error(f"Failed to get WM task {task_id}: {e}")
            return None

    def create_task(self, task: WarehouseTask) -> WarehouseTask | None:
        bwlvs = task.movement_type or "999"
        trart = task.transfer_type or self._derive_transfer_type(task.task_type)

        params = {
            "I_LGNUM": task.warehouse,
            "I_TANUM": "",
            "I_BWLVS": bwlvs,
            "I_TRART": trart,
            "I_MATNR": task.product or "",
            "I_WERKS": task.plant or "",
            "I_LGORT": task.storage_location or "",
            "I_VLTYP": self._get_source_type_prefix(task.source_bin),
            "I_VLPLA": task.source_bin or "",
            "I_NLTYP": self._get_source_type_prefix(task.dest_bin),
            "I_NLPLA": task.dest_bin or "",
            "I_ANFME": task.target_qty,
            "I_ALTME": task.uom or "EA",
            "I_CHARG": task.batch or "",
        }
        params = {k: v for k, v in params.items() if v != ""}

        try:
            result = self._call_rfc("L_TO_CREATE_SINGLE", **params)
            tanum = str(result.get("E_TANUM", ""))
            if tanum:
                logger.info(f"Created WM TO {tanum} for {task.product}")
                task.external_id = tanum
                task.to_number = tanum
                return task
            logger.error(f"L_TO_CREATE_SINGLE returned no TO number: {result}")
            return None
        except Exception as e:
            logger.error(f"Failed to create WM TO: {e}")
            return None

    def confirm_task(self, warehouse: str, task_id: str, qty: float,
                     item_no: str = "0001") -> bool:
        try:
            self._call_rfc(
                "L_TO_CONFIRM",
                I_LGNUM=warehouse,
                I_TANUM=task_id,
                I_TAPOS=item_no,
                I_WSMENG=qty,
                I_BUDAT=time.strftime("%Y%m%d"),
                I_WERKS=self._cfg.get("plant", ""),
                I_LGORT=self._cfg.get("storage_location", ""),
            )
            logger.info(f"Confirmed WM TO {task_id} qty={qty}")
            return True
        except Exception as e:
            logger.error(f"Failed to confirm WM TO {task_id}: {e}")
            return False

    def cancel_task(self, warehouse: str, task_id: str, item_no: str = "0001") -> bool:
        try:
            self._call_rfc(
                "L_TO_CANCEL",
                I_LGNUM=warehouse,
                I_TANUM=task_id,
            )
            logger.info(f"Cancelled WM TO {task_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel WM TO {task_id}: {e}")
            return False

    # ── Health ───────────────────────────────────────────

    def check_connection(self) -> dict:
        if self._mode == "http":
            try:
                client = self._get_http_client()
                resp = client.get("/health")
                data = resp.json()
                return {
                    "connected": resp.status_code == 200,
                    "backend": self.backend_type,
                    "mode": "http",
                    "warehouse_configured": bool(self._simulator_url),
                    "details": {
                        "simulator_url": self._simulator_url,
                        "tos_created": data.get("tos_created", 0),
                    },
                }
            except Exception as e:
                return {
                    "connected": False,
                    "backend": self.backend_type,
                    "mode": "http",
                    "warehouse_configured": bool(self._simulator_url),
                    "error": str(e)[:200],
                }

        try:
            self._call_rfc("RFC_PING")
            return {
                "connected": True,
                "backend": self.backend_type,
                "mode": "rfc",
                "warehouse_configured": bool(self._conn_params.get("user")),
                "details": {
                    "host": self._conn_params.get("ashost", ""),
                    "client": self._conn_params.get("client", ""),
                },
            }
        except ImportError:
            return {
                "connected": False,
                "backend": self.backend_type,
                "mode": "rfc",
                "warehouse_configured": bool(self._conn_params.get("user")),
                "error": "pyrfc not installed — SAP NW RFC SDK required",
            }
        except Exception as e:
            return {
                "connected": False,
                "backend": self.backend_type,
                "mode": "rfc",
                "warehouse_configured": bool(self._conn_params.get("user")),
                "error": str(e)[:200],
            }

    # ── Lifecycle ────────────────────────────────────────

    def close(self):
        """Release pyrfc and httpx connections."""
        if self._http_client is not None:
            try:
                self._http_client.close()
            except Exception:
                pass
            self._http_client = None
        self._close_rfc_connection()
        logger.debug("WmBackend connections closed")

    def validate_config(self) -> list[str]:
        errors = []
        if self._mode == "http":
            if not self._cfg.get("simulator_url") and not DEFAULT_WM_SIMULATOR_URL:
                errors.append("WM simulator URL not configured")
            return errors

        if not self._conn_params.get("ashost"):
            errors.append("WM RFC ashost not configured")
        if not self._conn_params.get("user"):
            errors.append("WM RFC user not configured")
        if not self._conn_params.get("passwd"):
            errors.append("WM RFC password not configured")
        return errors

    # ── Helpers ──────────────────────────────────────────

    def _get_to_items(self, warehouse: str, tanum: str) -> list[dict]:
        try:
            result = self._call_rfc("L_TO_READ", I_LGNUM=warehouse, I_TANUM=tanum)
            return self._extract_table(result, "T_ITEMS", [])
        except Exception:
            return []

    def _parse_to(self, row: dict, warehouse: str) -> WarehouseTask:
        tanum = str(row.get("TANUM", row.get("I_TANUM", "")))
        tapos = str(row.get("TAPOS", row.get("I_TAPOS", "0001")))
        bwlvs = str(row.get("BWLVS", row.get("I_BWLVS", "999")))
        trart = str(row.get("TRART", row.get("I_TRART", "U")))
        raw_status = str(row.get("STATUS", row.get("I_STATUS", "0")))

        return WarehouseTask(
            source_system="WM",
            warehouse=warehouse,
            external_id=tanum,
            item_no=tapos,
            task_type=MOVEMENT_TYPE_MAP.get(bwlvs, TRANSFER_TYPE_MAP.get(trart, "MOVE")),
            source_bin=row.get("VLPLA", row.get("I_VLPLA")),
            dest_bin=row.get("NLPLA", row.get("I_NLPLA")),
            product=row.get("MATNR", row.get("I_MATNR")),
            batch=row.get("CHARG", row.get("I_CHARG")),
            target_qty=float(row.get("ANFME", row.get("I_ANFME", 0)) or 0),
            actual_qty=float(row.get("WSMENG", row.get("I_WSMENG", 0)) or 0),
            uom=row.get("ALTME", row.get("I_ALTME", "EA")),
            status=raw_status,
            vendor_data={
                "to_number": tanum,
                "movement_type": bwlvs,
                "transfer_type": trart,
                "plant": row.get("WERKS", row.get("I_WERKS")),
                "storage_location": row.get("LGORT", row.get("I_LGORT")),
                "raw": row,
            },
        )

    @staticmethod
    def _derive_transfer_type(task_type: str) -> str:
        mapping = {"PICK": "A", "PUT": "E", "MOVE": "U", "CHARGE": "U"}
        return mapping.get(task_type.upper(), "U")

    @staticmethod
    def _extract_table(result: dict, key: str, default: list) -> list:
        table = result.get(key, default)
        if isinstance(table, list):
            return table
        if hasattr(table, "__iter__"):
            return list(table)
        return default

    @staticmethod
    def _get_source_type_prefix(bin_id: str | None) -> str:
        if not bin_id or len(bin_id) < 3:
            return "001"
        return bin_id[:3]
