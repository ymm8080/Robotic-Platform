"""
SAP IDoc listener — accepts XML IDoc push from SAP EWM/WM, parses to WarehouseTask.

Supports standard IDoc XML format with EDI_DC40 control record.
Target segment types (configurable):
  - E1WDHU01 / E1WLT01 (WM transfer order items)
  - ZEWM_WHORDER (EWM warehouse order segments — custom)
  - Generic fallback: extracts product/movement data from any segment

Usage:
  POST /api/v1/idoc  (Content-Type: application/xml)
  Returns 202 Accepted on successful parse + enqueue.
"""

import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime
from xml.etree import ElementTree as ET

from dispatch_queue import PriorityQueue
from models.order import WarehouseOrder
from models.warehouse_task import WarehouseTask
from redis_client import redis_from_url
from services.order_service import OrderService

logger = logging.getLogger(__name__)

# Redis URL for outbox / audit logging
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# Maximum IDoc XML payload size (1 MB) to prevent memory bombs.
MAX_IDOC_SIZE_BYTES = int(os.getenv("MAX_IDOC_SIZE_BYTES", "1048576"))

# Patterns that indicate a DTD/ENTITY declaration and therefore possible XXE.
_DTD_PATTERN = re.compile(r"<!\s*(DOCTYPE|ENTITY|ELEMENT|ATTLIST|NOTATION)", re.IGNORECASE)

# Namespace for IDoc XML (SAP uses unqualified elements, no namespace needed)
IDOC_ROOT_TAG = "IDOC"
CTRL_RECORD_TAG = "EDI_DC40"

# Segment-to-ProcessType mapping (data-driven, extendable)
SEGMENT_TASK_TYPES = {
    "E1WDHU01": "PUT",
    "E1WLT01": "PICK",
    "E1WLK01": "MOVE",
    "E1WEZ01": "MOVE",
    "ZEWM_WHORDER": "MOVE",
}


def _ns(tag: str) -> str:
    """Return unqualified tag (strip any namespace prefix)."""
    return tag[tag.rfind("}") + 1 :] if "}" in tag else tag


def _parse_date(d: str) -> str:
    """Parse SAP date YYYYMMDD → ISO YYYY-MM-DD."""
    d = (d or "").strip()
    if len(d) == 8:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    return d


def _parse_time(t: str) -> str:
    """Parse SAP time HHMMSS → ISO HH:MM:SS."""
    t = (t or "").strip()
    if len(t) == 6:
        return f"{t[:2]}:{t[2:4]}:{t[4:6]}"
    return t


def _has_idoc_format(raw: str) -> bool:
    """Quick check if payload looks like an SAP IDoc XML."""
    return IDOC_ROOT_TAG in raw and CTRL_RECORD_TAG in raw


def _extract_edi_dc40(root: ET.Element) -> dict:
    """Extract EDI_DC40 control record fields."""
    ctrl = root.find(CTRL_RECORD_TAG)
    if ctrl is None:
        ctrl = root.find(f".//{CTRL_RECORD_TAG}")
    if ctrl is None:
        return {}

    dc40 = {}
    for child in ctrl:
        tag = _ns(child.tag)
        dc40[tag] = (child.text or "").strip()
    return dc40


def _extract_segments(root: ET.Element) -> list[dict]:
    """Extract all data segments (skip EDI_DC40)."""
    segments = []
    for child in root:
        tag = _ns(child.tag)
        if tag == CTRL_RECORD_TAG:
            continue
        fields = {}
        for seg_child in child:
            seg_tag = _ns(seg_child.tag)
            fields[seg_tag] = (seg_child.text or "").strip()
        fields["_segment_type"] = tag
        segments.append(fields)
    return segments


def _segment_to_warehouse_task(segment: dict, dc40: dict) -> WarehouseTask | None:
    """Convert one IDoc data segment to WarehouseTask."""
    seg_type = segment.get("_segment_type", "")

    # Skip non-data segments (only skip the EDI_DC40 control record)
    if not seg_type or seg_type == "EDI_DC40":
        return None

    task_type = SEGMENT_TASK_TYPES.get(seg_type)
    if task_type is None:
        logger.debug(f"Unknown segment type '{seg_type}' — skipping")
        return None
    product = segment.get("MATNR", "") or segment.get("MATERIAL", "") or segment.get("PRODUCT", "") or ""
    source_bin = segment.get("VLPLA", "") or segment.get("SOURCE_BIN", "") or segment.get("LGPLA", "") or ""
    dest_bin = segment.get("NLPLA", "") or segment.get("DEST_BIN", "") or segment.get("NLEPL", "") or ""
    warehouse = segment.get("LGNUM", "") or segment.get("WERKS", "") or segment.get("WAREHOUSE", "") or "WM01"
    batch = segment.get("CHARG", "") or segment.get("BATCH", "") or ""
    qty_str = segment.get("PLQT1", "") or segment.get("TARGET_QTY", "") or "0"
    uom = segment.get("MEINS", "") or segment.get("UOM", "") or "EA"
    external_id = (
        segment.get("TANUM", "")
        or segment.get("TASK_ID", "")
        or segment.get("IDOC_NUMBER", "")
        or dc40.get("IDOC_NUMBER", "")
    )

    try:
        target_qty = float(qty_str) if qty_str else 0.0
    except ValueError:
        target_qty = 0.0

    if not external_id and not product:
        logger.debug(f"Skipping segment {seg_type}: no external_id or product")
        return None

    source_system = "EWM" if dc40.get("MESTYP", "").startswith("ZEWM") else "WM"

    return WarehouseTask(
        source_system=source_system,
        warehouse=warehouse,
        external_id=external_id or f"IDOC-{uuid.uuid4().hex[:8].upper()}",
        task_type=task_type,
        source_bin=source_bin or None,
        dest_bin=dest_bin or None,
        product=product or None,
        batch=batch or None,
        target_qty=target_qty,
        uom=uom,
        status="0",
    )


def _task_to_order(task: WarehouseTask) -> WarehouseOrder:
    """Convert WarehouseTask to WarehouseOrder for dispatch queue."""
    return WarehouseOrder(
        order_no=task.external_id,
        source=task.external_id,
        priority=2,
        payload=task.to_dict(),
        location=task.source_bin or task.dest_bin or "",
    )


class IdocListener:
    """SAP IDoc listener — parse, validate, enrich, and enqueue warehouse tasks."""

    def __init__(self, redis_url: str = REDIS_URL):
        self._redis = redis_from_url(redis_url, decode_responses=True)
        self._queue = PriorityQueue(redis_url)
        self._order_service = OrderService()
        self._stats_key = "idoc:stats"
        self._idoc_log_key = "idoc:recent"

    # ── Public API ─────────────────────────────────────

    def process(self, raw_xml: str) -> dict:
        """Process an incoming IDoc XML. Returns result summary."""
        if len(raw_xml.encode("utf-8")) > MAX_IDOC_SIZE_BYTES:
            logger.warning("IDoc payload exceeds maximum size")
            return {"accepted": False, "reason": "PAYLOAD_TOO_LARGE"}

        if _DTD_PATTERN.search(raw_xml):
            logger.warning("IDoc payload contains DTD/ENTITY declarations (XXE risk)")
            return {"accepted": False, "reason": "DTD_NOT_ALLOWED"}

        if not _has_idoc_format(raw_xml):
            logger.warning("Received payload that does not look like SAP IDoc XML")
            return {"accepted": False, "reason": "NOT_IDOC_XML"}

        try:
            root = ET.fromstring(raw_xml)
        except ET.ParseError as e:
            logger.warning(f"XML parse error: {e}")
            self._incr_stat("parse_errors")
            return {"accepted": False, "reason": f"XML_PARSE_ERROR: {e}"}

        dc40 = _extract_edi_dc40(root)
        segments = _extract_segments(root)

        if not segments:
            logger.warning(f"IDoc {dc40.get('IDOC_NUMBER', '?')}: no data segments found")
            self._incr_stat("empty_idocs")
            return {"accepted": False, "reason": "NO_DATA_SEGMENTS"}

        tasks = []
        orders = []
        errors = []

        for seg in segments:
            try:
                task = _segment_to_warehouse_task(seg, dc40)
                if task is None:
                    continue
                order = _task_to_order(task)

                # Persist before enqueue so the worker can load it from DB.
                self._order_service.create_order(order)

                # Enqueue
                self._queue.enqueue(order.order_no, order.priority, order.payload)

                tasks.append(task)
                orders.append(order)

            except Exception as e:
                seg_type = seg.get("_segment_type", "?")
                logger.error(f"Error processing segment {seg_type}: {e}")
                errors.append({"segment": seg_type, "error": str(e)})

        # Audit log
        self._log_idoc(dc40, len(tasks), len(errors))
        self._incr_stat("total_idocs")
        if errors:
            self._incr_stat("partial_errors")
        self._incr_stat("tasks_created", len(tasks))

        result = {
            "accepted": True,
            "messageType": dc40.get("MESTYP", "UNKNOWN"),
            "idocNumber": dc40.get("IDOC_NUMBER", ""),
            "tasksCreated": len(tasks),
            "segmentsProcessed": len(segments),
            "errors": errors if errors else None,
            "warehouse": tasks[0].warehouse if tasks else None,
        }
        logger.info(f"IDoc {result['idocNumber']}: {result['messageType']} → {len(tasks)} tasks, {len(errors)} errors")
        return result

    # ── Internal ───────────────────────────────────────

    def _incr_stat(self, key: str, amount: int = 1):
        try:
            today = datetime.now(UTC).strftime("%Y%m%d")
            self._redis.incr(f"idoc:stats:{today}:{key}", amount)
        except Exception:
            pass

    def _log_idoc(self, dc40: dict, task_count: int, error_count: int):
        """Log recent IDoc for debugging."""
        try:
            entry = {
                "idocNumber": dc40.get("IDOC_NUMBER", ""),
                "messageType": dc40.get("MESTYP", ""),
                "sender": dc40.get("SNDPOR", ""),
                "timestamp": datetime.now(UTC).isoformat(),
                "tasksCreated": task_count,
                "errors": error_count,
            }
            pipe = self._redis.pipeline()
            pipe.lpush(self._idoc_log_key, json.dumps(entry))
            pipe.ltrim(self._idoc_log_key, 0, 99)
            pipe.execute()
        except Exception:
            pass

    def get_stats(self) -> dict:
        """Get IDoc processing statistics."""
        stats = {}
        try:
            today = datetime.now(UTC).strftime("%Y%m%d")
            keys = self._redis.keys(f"idoc:stats:{today}:*") or []
            for k in keys:
                name = k.split(":", 3)[-1]
                val = self._redis.get(k)
                stats[name] = int(val) if val else 0
        except Exception:
            pass
        return stats

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return recent IDoc log entries."""
        try:
            data = self._redis.lrange(self._idoc_log_key, 0, n - 1) or []
            return [json.loads(d) for d in data]
        except Exception:
            return []
