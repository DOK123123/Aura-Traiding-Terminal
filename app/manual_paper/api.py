"""Manual Paper v1 API scaffold. NOT mounted in app.main.

Read-only contract only until durable storage, server-fetched verified quotes,
owner authentication, CSRF and idempotent atomic commands are integrated.
Do not accept client-submitted execution prices or use retired /api/paper.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/manual-paper", tags=["Manual Paper prototype"])

@router.get("/capabilities")
async def capabilities():
    return {
        "mode": "MANUAL_PAPER_PROTOTYPE",
        "virtual_only": True,
        "real_money_execution": "DISABLED",
        "ready": False,
        "manual_orders_enabled": False,
        "reason": "SERVER_QUOTE_AUTH_PERSISTENCE_NOT_INTEGRATED",
        "balance": None,
        "position": None,
    }

@router.post("/orders")
async def unavailable_open():
    raise HTTPException(status_code=503, detail="MANUAL_PAPER_NOT_READY")

@router.post("/positions/{position_id}/close")
async def unavailable_close(position_id: str):
    raise HTTPException(status_code=503, detail="MANUAL_PAPER_NOT_READY")
