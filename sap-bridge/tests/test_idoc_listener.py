"""Tests for SAP IDoc listener — XML parse, task extraction, enqueue."""
import os
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest

from services.idoc_listener import IdocListener, _extract_edi_dc40, _extract_segments, _segment_to_warehouse_task

# Redis URL for tests: honour REDIS_URL_TEST first (local dev override),
# then CI's REDIS_URL, then a password‑free localhost default on DB 1.
_REDIS_BASE = os.getenv("REDIS_URL_TEST") or os.getenv("REDIS_URL", "redis://localhost:6379/1")
REDIS_URL = _REDIS_BASE

# ── Mock Redis (same pattern as test_worker.py) ────────

_MOCK_REDIS = MagicMock()
_MOCK_REDIS.ping.return_value = True
_MOCK_REDIS.zadd.return_value = 1
_MOCK_REDIS.zcard.return_value = 0
_MOCK_REDIS.zrange.return_value = []
_MOCK_REDIS.zrem.return_value = 1
_MOCK_REDIS.hset.return_value = 1
_MOCK_REDIS.hgetall.return_value = {}
_MOCK_REDIS.hdel.return_value = 1
_MOCK_REDIS.expire.return_value = True
_MOCK_REDIS.delete.return_value = 1
_MOCK_REDIS.get.return_value = None
_MOCK_REDIS.set.return_value = True
_MOCK_REDIS.setex.return_value = True
_MOCK_REDIS.incr.return_value = 1
_MOCK_REDIS.keys.return_value = []
_MOCK_REDIS.lrange.return_value = []
_MOCK_REDIS.lpush.return_value = 1
_MOCK_REDIS.ltrim.return_value = True
_MOCK_REDIS.pipeline.return_value = _MOCK_REDIS  # pipe is the mock itself
_MOCK_REDIS.execute.return_value = None


@pytest.fixture(autouse=True)
def _patch_redis():
    """Patch redis.from_url globally so IdocListener + PriorityQueue use mocks."""
    with patch("redis.from_url", return_value=_MOCK_REDIS):
        yield

# ── Sample IDoc payloads ──────────────────────────────

SAMPLE_IDOC_WM = """<?xml version="1.0" encoding="UTF-8"?>
<IDOC>
  <EDI_DC40>
    <IDOC_NUMBER>0000012345</IDOC_NUMBER>
    <MESTYP>WEADM</MESTYP>
    <SNDPOR>SAPWM</SNDPOR>
    <SNDPRT>LS</SNDPRT>
    <RCVPOR>ROBOT_PLATFORM</RCVPOR>
    <RCVPRT>LS</RCVPRT>
    <CREDAT>20260625</CREDAT>
    <CRETIM>100000</CRETIM>
  </EDI_DC40>
  <E1WDHU01>
    <LGNUM>WM01</LGNUM>
    <TANUM>1000123</TANUM>
    <TAPOS>0001</TAPOS>
    <MATNR>MAT-WIDGET</MATNR>
    <CHARG>BATCH-A1</CHARG>
    <PLQT1>10.000</PLQT1>
    <MEINS>EA</MEINS>
    <VLTYP>001</VLTYP>
    <VLPLA>A-01-01</VLPLA>
    <NLTYP>002</NLTYP>
    <NLPLA>B-02-01</NLPLA>
  </E1WDHU01>
  <E1WDHU01>
    <LGNUM>WM01</LGNUM>
    <TANUM>1000124</TANUM>
    <TAPOS>0002</TAPOS>
    <MATNR>MAT-BOLT</MATNR>
    <PLQT1>5.000</PLQT1>
    <MEINS>EA</MEINS>
    <VLTYP>001</VLTYP>
    <VLPLA>A-01-02</VLPLA>
    <NLTYP>002</NLTYP>
    <NLPLA>B-02-02</NLPLA>
  </E1WDHU01>
</IDOC>"""

SAMPLE_IDOC_EWM = """<?xml version="1.0" encoding="UTF-8"?>
<IDOC>
  <EDI_DC40>
    <IDOC_NUMBER>0000067890</IDOC_NUMBER>
    <MESTYP>ZEWM_WAREHOUSE_TASK</MESTYP>
    <SNDPOR>EWM01</SNDPOR>
    <SNDPRT>LS</SNDPRT>
    <RCVPOR>ROBOT</RCVPOR>
    <RCVPRT>LS</RCVPRT>
    <CREDAT>20260625</CREDAT>
    <CRETIM>113000</CRETIM>
  </EDI_DC40>
  <ZEWM_WHORDER>
    <WAREHOUSE>EW01</WAREHOUSE>
    <TASK_ID>WT-5001</TASK_ID>
    <PRODUCT>MAT-GEAR</PRODUCT>
    <BATCH>B-2026</BATCH>
    <TARGET_QTY>25</TARGET_QTY>
    <UOM>EA</UOM>
    <SOURCE_BIN>IN-001</SOURCE_BIN>
    <DEST_BIN>OUT-001</DEST_BIN>
    <PROCESS_TYPE>PICK</PROCESS_TYPE>
  </ZEWM_WHORDER>
</IDOC>"""

INVALID_XML = """<?xml version="1.0"?><IDOC><EDI_DC40><IDOC_NUMBER>1<messed</EDI_DC40></IDOC>"""

NOT_IDOC = """{"status": "healthy"}"""


# ── Unit: EDI_DC40 extraction ────────────────────────

class TestExtractEdiDc40:
    def test_extracts_control_record(self):
        root = ET.fromstring(SAMPLE_IDOC_WM)
        dc40 = _extract_edi_dc40(root)
        assert dc40["IDOC_NUMBER"] == "0000012345"
        assert dc40["MESTYP"] == "WEADM"
        assert dc40["SNDPOR"] == "SAPWM"
        assert dc40["CREDAT"] == "20260625"

    def test_ewm_control_record(self):
        root = ET.fromstring(SAMPLE_IDOC_EWM)
        dc40 = _extract_edi_dc40(root)
        assert dc40["IDOC_NUMBER"] == "0000067890"
        assert dc40["MESTYP"] == "ZEWM_WAREHOUSE_TASK"

    def test_empty_no_ctrl_record(self):
        root = ET.fromstring("<IDOC><DUMMY><X>1</X></DUMMY></IDOC>")
        dc40 = _extract_edi_dc40(root)
        assert dc40 == {}


# ── Unit: Segment extraction ─────────────────────────

class TestExtractSegments:
    def test_extracts_wm_segments(self):
        root = ET.fromstring(SAMPLE_IDOC_WM)
        segs = _extract_segments(root)
        assert len(segs) == 2
        assert segs[0]["_segment_type"] == "E1WDHU01"
        assert segs[0]["MATNR"] == "MAT-WIDGET"

    def test_extracts_ewm_segments(self):
        root = ET.fromstring(SAMPLE_IDOC_EWM)
        segs = _extract_segments(root)
        assert len(segs) == 1
        assert segs[0]["_segment_type"] == "ZEWM_WHORDER"
        assert segs[0]["TASK_ID"] == "WT-5001"


# ── Unit: Segment → WarehouseTask ────────────────────

class TestSegmentToWarehouseTask:
    def test_wm_segment_conversion(self):
        root = ET.fromstring(SAMPLE_IDOC_WM)
        dc40 = _extract_edi_dc40(root)
        segs = _extract_segments(root)
        task = _segment_to_warehouse_task(segs[0], dc40)
        assert task is not None
        assert task.source_system == "WM"
        assert task.warehouse == "WM01"
        assert task.external_id == "1000123"
        assert task.task_type == "PUT"
        assert task.product == "MAT-WIDGET"
        assert task.batch == "BATCH-A1"
        assert task.target_qty == 10.0
        assert task.uom == "EA"
        assert task.source_bin == "A-01-01"
        assert task.dest_bin == "B-02-01"

    def test_ewm_segment_conversion(self):
        root = ET.fromstring(SAMPLE_IDOC_EWM)
        dc40 = _extract_edi_dc40(root)
        segs = _extract_segments(root)
        task = _segment_to_warehouse_task(segs[0], dc40)
        assert task is not None
        assert task.source_system == "EWM"
        assert task.warehouse == "EW01"
        assert task.external_id == "WT-5001"
        assert task.task_type == "MOVE"
        assert task.product == "MAT-GEAR"
        assert task.target_qty == 25.0

    def test_skips_empty_segment(self):
        task = _segment_to_warehouse_task({"_segment_type": "E1WDHU01"}, {})
        assert task is None


# ── Integration: IdocListener ────────────────────────

class TestIdocListener:
    def test_process_wm_idoc(self):
        listener = IdocListener(redis_url=REDIS_URL)
        result = listener.process(SAMPLE_IDOC_WM)
        assert result["accepted"] is True
        assert result["messageType"] == "WEADM"
        assert result["tasksCreated"] == 2
        assert result["idocNumber"] == "0000012345"

    def test_process_ewm_idoc(self):
        listener = IdocListener(redis_url=REDIS_URL)
        result = listener.process(SAMPLE_IDOC_EWM)
        assert result["accepted"] is True
        assert result["messageType"] == "ZEWM_WAREHOUSE_TASK"
        assert result["tasksCreated"] == 1

    def test_rejects_non_idoc(self):
        listener = IdocListener(redis_url=REDIS_URL)
        result = listener.process(NOT_IDOC)
        assert result["accepted"] is False
        assert "NOT_IDOC_XML" in result["reason"]

    def test_rejects_invalid_xml(self):
        listener = IdocListener(redis_url=REDIS_URL)
        result = listener.process(INVALID_XML)
        assert result["accepted"] is False

    def test_stats(self):
        listener = IdocListener(redis_url=REDIS_URL)
        stats = listener.get_stats()
        assert isinstance(stats, dict)

    def test_recent_empty(self):
        listener = IdocListener(redis_url=REDIS_URL)
        recent = listener.get_recent(5)
        assert isinstance(recent, list)
