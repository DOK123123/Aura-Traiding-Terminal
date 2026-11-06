"""Owner-only Web Push configuration. These POSTs cannot reach trading APIs."""
import json
import secrets
import time

from fastapi import APIRouter, HTTPException, Request, Query
from .web_push import subscription, subscription_id
from .lock_runtime import snapshot

router = APIRouter(prefix='/api/preview/push')
history_router = APIRouter(prefix='/api/preview/lock')
WRITE_PATHS = frozenset('/api/preview/push/'+x for x in ('subscribe', 'preferences', 'unsubscribe', 'test'))


def allowed_write(request: Request) -> bool:
    token = getattr(request.app.state, 'preview_ws_token', '')
    supplied = request.headers.get('X-Aura-Preview-Push', '')
    origin = str(request.base_url).rstrip('/')
    return (request.method == 'POST' and request.url.path in WRITE_PATHS and bool(token)
            and secrets.compare_digest(supplied, token)
            and request.headers.get('Origin') == origin
            and request.headers.get('Sec-Fetch-Site', 'same-origin') in ('same-origin', 'none')
            and request.headers.get('Content-Type', '').split(';')[0] == 'application/json')


def worker(request: Request):
    config = request.app.state.preview_config
    value = getattr(request.app.state, 'signal_lock', None)
    task = getattr(request.app.state, 'signal_lock_task', None)
    if (not config.push_enabled or value is None or value.sender is None or value.push_store is None
            or task is None or task.done() or value.error is not None):
        raise HTTPException(503, 'PREVIEW_PUSH_UNAVAILABLE')
    return value


async def body(request: Request) -> dict:
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 8192:
            raise HTTPException(413, 'PUSH_BODY_LIMIT')
    try:
        value = json.loads(data)
        if not isinstance(value, dict):
            raise ValueError()
        return value
    except (ValueError, UnicodeError):
        raise HTTPException(400, 'PUSH_BODY_FORMAT') from None


def checked_id(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise HTTPException(400, 'SUBSCRIPTION_ID_FORMAT')
    return value


def preferences(value: dict) -> dict:
    if type(value.get('candidate')) is not bool or type(value.get('watch')) is not bool:
        raise HTTPException(400, 'PUSH_PREFERENCE_FORMAT')
    return {'candidate': value['candidate'], 'watch': value['watch']}


async def call(value, action: str, data: dict | None = None):
    import asyncio
    try:
        return await asyncio.to_thread(value.push_store.call, action, data)
    except Exception:
        # Third-party errors may contain endpoints or private configuration.
        raise HTTPException(503, 'PUSH_STORAGE_UNAVAILABLE') from None


@router.get('/status')
async def status(request: Request, subscription_id: str | None = None):
    config = request.app.state.preview_config
    data = {'enabled': config.push_enabled, 'configured': False, 'real_android_delivery': 'UNKNOWN',
            'background': 'BEST_EFFORT_WHILE_RENDER_AWAKE',
            'limitations': 'Render Free может засыпать. В сон анализ не выполняется. Звук определяют Android и браузер.'}
    if not config.push_enabled:
        return data
    value = worker(request)
    data.update(configured=True, public_key=value.sender.public_key,
                lock_ready=snapshot(request.app)['ready'],delivery_error=value.delivery_error)
    sid = checked_id(subscription_id) if subscription_id is not None else ''
    data['diagnostics'] = await call(value, 'diagnostics', {'id': sid})
    return data


@router.post('/subscribe')
async def subscribe(request: Request):
    value, data = worker(request), await body(request)
    prefs = preferences(data)
    try:
        target = subscription(data.get('subscription'))
        sid = subscription_id(target)
    except (ValueError, TypeError):
        raise HTTPException(400, 'INVALID_PUSH_SUBSCRIPTION') from None
    return await call(value, 'subscribe', {'id': sid, 'target': target, **prefs})


@router.post('/preferences')
async def update_preferences(request: Request):
    value, data = worker(request), await body(request)
    return await call(value, 'preferences', {'id': checked_id(data.get('id')), **preferences(data)})


@router.post('/unsubscribe')
async def unsubscribe(request: Request):
    value, data = worker(request), await body(request)
    return await call(value, 'unsubscribe', {'id': checked_id(data.get('id'))})


@router.post('/test')
async def test(request: Request):
    value, data = worker(request), await body(request)
    sid = checked_id(data.get('id'))
    diagnostic = await call(value, 'diagnostics', {'id': sid})
    if not diagnostic.get('subscription'):
        raise HTTPException(404, 'SUBSCRIPTION_NOT_FOUND')
    now = time.time()
    payload = {'event_id': secrets.token_hex(32), 'status': 'TEST', 'direction': 'LONG',
               'frame': '15m', 'score': 0, 'at': now, 'expires_at': now+60, 'subscription_id': sid}
    result = await call(value, 'test', payload)
    return {**result, 'device_delivery': 'NOT_CONFIRMED', 'code': result.get('code', 'TEST_QUEUED_NOT_DEVICE_CONFIRMED')}


@history_router.get('/history')
async def history(request: Request, before: float = Query(1e11,ge=0,le=1e11),
                  frame: str | None = Query(None,pattern='^(5m|15m|1h|4h)$'), limit: int = Query(50,ge=1,le=100),
                  before_id: str = Query('f'*64,pattern='^[a-f0-9]{64}$')):
    import asyncio
    from .signal_lock import project
    value = getattr(request.app.state, 'signal_lock', None)
    if value is None or not request.app.state.preview_config.lock_enabled:
        raise HTTPException(503, 'SIGNAL_HISTORY_UNAVAILABLE')
    try:
        rows = await asyncio.to_thread(value.store.history,before,frame,limit,before_id)
        data=[]
        for row in rows:
            item=project(row,time.time())
            item.update(archived=True,plan=None)
            data.append(item)
        return {'events':data,'next_before':data[-1]['detected_at'] if data else None,'next_before_id':data[-1]['id'] if data else None}
    except Exception:
        raise HTTPException(503,'SIGNAL_HISTORY_UNAVAILABLE') from None


@history_router.get('/event/{event_id}')
async def event(request: Request,event_id: str):
    import asyncio
    from .signal_lock import project
    key=checked_id(event_id)
    value=getattr(request.app.state,'signal_lock',None)
    if value is None or not request.app.state.preview_config.lock_enabled:raise HTTPException(503,'SIGNAL_HISTORY_UNAVAILABLE')
    try:row=await asyncio.to_thread(value.store.event,key)
    except Exception:raise HTTPException(503,'SIGNAL_HISTORY_UNAVAILABLE') from None
    if row is None:raise HTTPException(404,'SIGNAL_EVENT_NOT_FOUND')
    result=project(row,time.time());result.update(archived=True,plan=None)
    return result
