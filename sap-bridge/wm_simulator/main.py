"""SAP WM RFC Simulator — FastAPI server mimicking L_TO_* RFC function modules.

Endpoints mirror the RFC calls made by WmBackend:
  POST /rfc/L_TO_READ           -> list/get TO headers + items
  POST /rfc/L_TO_CREATE_SINGLE  -> create Transfer Order
  POST /rfc/L_TO_CONFIRM        -> confirm TO
  POST /rfc/L_TO_CANCEL         -> cancel TO
  GET  /rfc/ping                -> RFC_PING equivalent

Run standalone:
  uvicorn wm_simulator.main:app --host 0.0.0.0 --port 8001

Run via Docker Compose:
  docker compose up wm-simulator -d
"""

import logging
import time
from datetime import UTC, datetime

from fastapi import FastAPI
from pydantic import BaseModel

logger = logging.getLogger(__name__)

app = FastAPI(title="SAP WM RFC Simulator", version="1.0.0")

# ── In-memory TO store ──────────────────────────────────────────
_tos: dict[str, dict] = {}
_next_tanum = 1000000


def _next_tanum() -> str:
    global _next_tanum
    _next_tanum += 1
    return str(_next_tanum)


# ── Data models ─────────────────────────────────────────────────

class ToHeader(BaseModel):
    TANUM: str = ""
    STATUS: str = "0"
    BWLVS: str = "999"
    TRART: str = "U"
    MATNR: str = ""
    VLPLA: str = ""
    NLPLA: str = ""
    ANFME: float = 0
    ALTME: str = "EA"
    CHARG: str = ""
    WERKS: str = "1000"
    LGORT: str = "0001"
    LGNUM: str = "001"


class ToItem(BaseModel):
    TAPOS: str = "0001"
    MATNR: str = ""
    ANFME: float = 0
    ALTME: str = "EA"
    CHARG: str = ""
    VLPLA: str = ""
    NLPLA: str = ""
    BWLVS: str = "999"


class LToReadRequest(BaseModel):
    I_LGNUM: str = "001"
    I_TANUM: str = ""


class LToCreateSingleRequest(BaseModel):
    I_LGNUM: str = "001"
    I_TANUM: str = ""
    I_BWLVS: str = "999"
    I_TRART: str = "U"
    I_MATNR: str = ""
    I_WERKS: str = "1000"
    I_LGORT: str = "0001"
    I_VLTYP: str = ""
    I_VLPLA: str = ""
    I_NLTYP: str = ""
    I_NLPLA: str = ""
    I_ANFME: float = 0
    I_ALTME: str = "EA"
    I_CHARG: str = ""


class LToConfirmRequest(BaseModel):
    I_LGNUM: str = "001"
    I_TANUM: str = ""
    I_TAPOS: str = "0001"
    I_WSMENG: float = 0
    I_BUDAT: str = ""
    I_WERKS: str = "1000"
    I_LGORT: str = "0001"


class LToCancelRequest(BaseModel):
    I_LGNUM: str = "001"
    I_TANUM: str = ""


# ── RFC Endpoints ───────────────────────────────────────────────

@app.post("/rfc/ping")
async def rfc_ping():
    """RFC_PING equivalent — connection test."""
    return {
        "E_RESULT": 0,
        "E_MESSAGE": "RFC_PING successful",
        "TIMESTAMP": datetime.now(UTC).isoformat(),
    }


@app.post("/rfc/L_TO_READ")
async def l_to_read(req: LToReadRequest):
    """Read transfer orders. No I_TANUM = list all, with I_TANUM = get one."""
    logger.info(f"L_TO_READ: LGNUM={req.I_LGNUM} TANUM={req.I_TANUM}")

    if req.I_TANUM:
        # Get specific TO
        to_data = _tos.get(req.I_TANUM)
        if not to_data:
            # Return some default mock data for known test numbers
            if req.I_TANUM == "1000001":
                to_data = {
                    "tanum": "1000001", "status": "0", "bwlvs": "201", "trart": "A",
                    "matnr": "MAT-A", "vlpla": "AA-01", "nlpla": "BB-02",
                    "anfme": 5.0, "altme": "EA", "charg": "BATCH01",
                    "werks": "1000", "lgort": "0001", "lgnum": req.I_LGNUM,
                    "items": [
                        {"tapos": "0001", "matnr": "MAT-A", "anfme": 5.0,
                         "altme": "EA", "vlpla": "AA-01", "nlpla": "BB-02",
                         "bwlvs": "201", "charg": "BATCH01"},
                    ],
                }
            else:
                return {"T_HEADERS": [], "T_ITEMS": []}

        # Build response
        headers = [{
            "TANUM": to_data["tanum"],
            "STATUS": to_data["status"],
            "BWLVS": to_data["bwlvs"],
            "TRART": to_data["trart"],
            "MATNR": to_data["matnr"],
            "VLPLA": to_data["vlpla"],
            "NLPLA": to_data["nlpla"],
            "ANFME": to_data["anfme"],
            "ALTME": to_data["altme"],
            "CHARG": to_data.get("charg", ""),
            "WERKS": to_data.get("werks", "1000"),
            "LGORT": to_data.get("lgort", "0001"),
        }]
        items = [{
            "TANUM": to_data["tanum"],
            "TAPOS": it["tapos"],
            "MATNR": it["matnr"],
            "ANFME": it["anfme"],
            "ALTME": it.get("altme", "EA"),
            "VLPLA": it.get("vlpla", ""),
            "NLPLA": it.get("nlpla", ""),
            "BWLVS": it.get("bwlvs", "999"),
            "CHARG": it.get("charg", ""),
        } for it in to_data.get("items", [])]
        return {"T_HEADERS": headers, "T_ITEMS": items}

    else:
        # List all TOs for this warehouse, filter by status logic
        matching = []
        for tanum, to_data in sorted(_tos.items()):
            if to_data.get("lgnum") == req.I_LGNUM:
                matching.append(to_data)

        # If no TOs in store, return mock data for demo
        if not matching:
            matching = [
                {
                    "tanum": "3000001", "status": "0", "bwlvs": "201", "trart": "A",
                    "matnr": "MAT-A", "vlpla": "AA-01", "nlpla": "BB-02",
                    "anfme": 5.0, "altme": "EA", "charg": "BATCH01",
                    "werks": "1000", "lgort": "0001", "lgnum": req.I_LGNUM,
                    "items": [
                        {"tapos": "0001", "matnr": "MAT-A", "anfme": 5.0,
                         "altme": "EA", "vlpla": "AA-01", "nlpla": "BB-02",
                         "bwlvs": "201", "charg": "BATCH01"},
                    ],
                },
                {
                    "tanum": "3000002", "status": "0", "bwlvs": "101", "trart": "E",
                    "matnr": "MAT-B", "vlpla": "CC-01", "nlpla": "DD-02",
                    "anfme": 3.0, "altme": "EA", "charg": "",
                    "werks": "1000", "lgort": "0001", "lgnum": req.I_LGNUM,
                    "items": [
                        {"tapos": "0001", "matnr": "MAT-B", "anfme": 3.0,
                         "altme": "EA", "vlpla": "CC-01", "nlpla": "DD-02",
                         "bwlvs": "101", "charg": ""},
                    ],
                },
            ]

        headers = [{
            "TANUM": td["tanum"], "STATUS": td["status"],
            "BWLVS": td["bwlvs"], "TRART": td["trart"],
            "MATNR": td["matnr"], "VLPLA": td["vlpla"],
            "NLPLA": td["nlpla"], "ANFME": td["anfme"],
            "ALTME": td["altme"], "CHARG": td.get("charg", ""),
            "WERKS": td.get("werks", "1000"), "LGORT": td.get("lgort", "0001"),
        } for td in matching]
        items = []
        for td in matching:
            for it in td.get("items", []):
                items.append({
                    "TANUM": td["tanum"], "TAPOS": it["tapos"],
                    "MATNR": it["matnr"], "ANFME": it["anfme"],
                    "ALTME": it.get("altme", "EA"),
                    "VLPLA": it.get("vlpla", ""), "NLPLA": it.get("nlpla", ""),
                    "BWLVS": it.get("bwlvs", "999"), "CHARG": it.get("charg", ""),
                })

        return {"T_HEADERS": headers, "T_ITEMS": items}


@app.post("/rfc/L_TO_CREATE_SINGLE")
async def l_to_create_single(req: LToCreateSingleRequest):
    """Create a new transfer order."""
    tanum = _next_tanum()
    logger.info(f"L_TO_CREATE_SINGLE: TANUM={tanum} MATNR={req.I_MATNR}")

    to_data = {
        "tanum": tanum,
        "status": "0",
        "bwlvs": req.I_BWLVS,
        "trart": req.I_TRART,
        "matnr": req.I_MATNR,
        "vlpla": req.I_VLPLA,
        "nlpla": req.I_NLPLA,
        "anfme": req.I_ANFME,
        "altme": req.I_ALTME,
        "charg": req.I_CHARG,
        "werks": req.I_WERKS,
        "lgort": req.I_LGORT,
        "lgnum": req.I_LGNUM,
        "items": [{
            "tapos": "0001", "matnr": req.I_MATNR,
            "anfme": req.I_ANFME, "altme": req.I_ALTME,
            "vlpla": req.I_VLPLA, "nlpla": req.I_NLPLA,
            "bwlvs": req.I_BWLVS, "charg": req.I_CHARG,
        }],
        "created_at": datetime.now(UTC).isoformat(),
    }
    _tos[tanum] = to_data

    return {"E_TANUM": tanum, "E_SUBRC": 0, "E_MESSAGE": "TO created successfully"}


@app.post("/rfc/L_TO_CONFIRM")
async def l_to_confirm(req: LToConfirmRequest):
    """Confirm a transfer order (mark as done)."""
    logger.info(f"L_TO_CONFIRM: TANUM={req.I_TANUM} qty={req.I_WSMENG}")

    to_data = _tos.get(req.I_TANUM)
    if to_data:
        to_data["status"] = "2"  # Confirmed
        to_data["confirmed_qty"] = req.I_WSMENG
        to_data["confirmed_at"] = datetime.now(UTC).isoformat()

    return {"E_SUBRC": 0, "E_MESSAGE": f"TO {req.I_TANUM} confirmed"}


@app.post("/rfc/L_TO_CANCEL")
async def l_to_cancel(req: LToCancelRequest):
    """Cancel a transfer order."""
    logger.info(f"L_TO_CANCEL: TANUM={req.I_TANUM}")

    to_data = _tos.get(req.I_TANUM)
    if to_data:
        to_data["status"] = "3"  # Cancelled
        to_data["cancelled_at"] = datetime.now(UTC).isoformat()

    return {"E_SUBRC": 0, "E_MESSAGE": f"TO {req.I_TANUM} cancelled"}


@app.get("/health")
async def health():
    """Health check for Docker healthcheck."""
    return {
        "status": "healthy",
        "tos_created": len(_tos),
        "uptime_seconds": int(time.time() - _start_time),
    }


@app.get("/admin/tos")
async def list_tos():
    """List all transfer orders in the simulator (debug endpoint)."""
    return {
        "count": len(_tos),
        "transfer_orders": [
            {
                "tanum": k,
                "status": v["status"],
                "product": v.get("matnr", ""),
                "source": v.get("vlpla", ""),
                "dest": v.get("nlpla", ""),
                "qty": v.get("anfme", 0),
                "created": v.get("created_at", ""),
            }
            for k, v in sorted(_tos.items())
        ],
    }


@app.post("/admin/reset")
async def reset():
    """Reset simulator state (debug endpoint)."""
    _tos.clear()
    global _next_tanum
    _next_tanum = 1000000
    return {"status": "reset", "tos_cleared": True}


# ── Startup ──

_start_time = time.time()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
