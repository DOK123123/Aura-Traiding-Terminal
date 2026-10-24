"""Safe delivery logs for authenticated scheduler requests; no trading logic."""
import json
import logging
import os
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from app.paper.api import HEADERS

# Uvicorn's existing INFO handler is active in start_web.py. No global logging
# configuration or secret-bearing request/body dump is installed.
logger = logging.getLogger('uvicorn.error')
TICK_ID = re.compile(r'ACTIVE43_BITGET_[a-f0-9]{32}:tick:[0-9]{1,12}')


async def delivery(request: Request, operation, respond):
    ids = request.headers.getlist('X-Aura-Invocation-Id')
    if ids and (len(ids)!=1 or not re.fullmatch('[a-f0-9]{32}',ids[0]) or any(
            secrets.compare_digest(ids[0].encode(),os.getenv(name,'').encode()) for name in (
                'AURA_ACTIVE43_BITGET_SCHEDULER_SECRET','AURA_ACTIVE43_BITGET_SUPABASE_SERVICE_KEY',
                'AURA_TESTNET_VIEW_PASSWORD','AURA_AUTO42_SCHEDULER_SECRET'))):
        raise HTTPException(400,'INVALID_INVOCATION_ID',headers=HEADERS)
    invocation_id = ids[0] if ids else uuid.uuid4().hex
    started = time.monotonic()
    response = None
    body = {}
    completed = False
    try:
        response = await respond(operation())
        body = json.loads(response.body)
        completed = True
        return response
    finally:
        try:
            record(request,invocation_id,started,response.status_code if completed else 500,body)
        except Exception:
            # Logging is passive; it cannot change a committed financial outcome
            # or replace the engine's original exception with a logging failure.
            pass


def record(request, invocation_id, started, http_status, body):
    tick_id = body.get('tick_id')
    verified = body.get('tick_receipt_verified') is True and isinstance(tick_id,str) and bool(TICK_ID.fullmatch(tick_id))
    status = body.get('status') if body.get('status') in ('COMPLETED','PAUSED') else None
    # Whitelisted evidence only. Source exceptions, headers, state and raw bodies
    # are never logged. A saved PAUSED receipt is not a successful trading cycle.
    logger.info('ACTIVE43_TICK_DELIVERY %s',json.dumps(dict(
        event='TICK_SAVED' if verified and http_status==200 and status=='COMPLETED' else 'TICK_FAILED',
        invocation_id=invocation_id,utc=datetime.now(timezone.utc).isoformat(),
        http_status=http_status,operation='off_only' if request.url.path.endswith('/verify-off-tick') else 'saved_mode',
        tick_id=tick_id if verified else None,tick_created_at=body.get('tick_created_at') if verified else None,
        tick_slot_start=body.get('tick_slot_start') if verified else None,
        state_saved=verified and body.get('state_saved') is True,status=status,
        mode=body.get('mode') if body.get('mode') in ('ON','OFF','PAUSED','EMERGENCY') else None,
        duplicate=body.get('duplicate') if type(body.get('duplicate')) is bool else None,
        render_commit=body.get('render_commit') if isinstance(body.get('render_commit'),str) and re.fullmatch('[a-f0-9]{40}',body['render_commit']) else None,
        tick_render_commit=body.get('tick_render_commit') if isinstance(body.get('tick_render_commit'),str) and re.fullmatch('[a-f0-9]{40}',body['tick_render_commit']) else None,
        code='TICK_RECEIPT_CONFIRMED' if verified else 'TICK_NOT_CONFIRMED',
        duration_ms=round((time.monotonic()-started)*1000,3)),sort_keys=True))
