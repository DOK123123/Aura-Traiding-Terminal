"""Manual Paper v1 API scaffold. NOT mounted in app.main.

Read-only contract only until durable storage, server-fetched verified quotes,
owner authentication, CSRF and idempotent atomic commands are integrated.
Do not accept client-submitted execution prices or use retired /api/paper.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from app.paper.api import owner, HEADERS
from .bitget import fetch_verified_quote
from .quotes import QuoteRejected
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

@router.get("/quote", dependencies=[Depends(owner)])
async def quote(request: Request):
    if not hasattr(request.app.state, "client"):
        raise HTTPException(503, "MARKET_CLIENT_NOT_READY", headers=HEADERS)
    try:
        value = await fetch_verified_quote(request.app.state.client)
    except QuoteRejected as exc:
        raise HTTPException(503, str(exc), headers=HEADERS) from None
    return {"quote": {k: str(v) if k == "price" else v for k, v in value.items()},
            "read_only": True, "orders_enabled": False,
            "real_money_execution": "DISABLED"}

@router.post("/orders")
async def unavailable_open():
    raise HTTPException(status_code=503, detail="MANUAL_PAPER_NOT_READY")

@router.post("/positions/{position_id}/close")
async def unavailable_close(position_id: str):
    raise HTTPException(status_code=503, detail="MANUAL_PAPER_NOT_READY")
