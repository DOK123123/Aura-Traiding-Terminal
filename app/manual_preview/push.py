"""Owner-only Android Web Push, separate from all trading/account commands."""
import asyncio
import base64
import hashlib
import json
import os
import re
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey, SECP256R1
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from py_vapid import Vapid
from pywebpush import webpush, WebPushException
import requests

from .signal_store import SignalStore

router = APIRouter(prefix='/api/preview/push')
NAMES = ('AURA_PREVIEW_VAPID_PRIVATE_KEY', 'AURA_PREVIEW_VAPID_PUBLIC_KEY', 'AURA_PREVIEW_VAPID_SUBJECT')


def decode(value: str, length: int) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError('INVALID_PUSH_KEY')
    raw = base64.urlsafe_b64decode(value+'='*(-len(value) % 4))
    if len(raw) != length:
        raise ValueError('INVALID_PUSH_KEY')
    return raw


def subscription(value: dict) -> tuple[str, dict]:
    if not isinstance(value, dict) or not isinstance(value.get('keys'), dict):
        raise ValueError('INVALID_SUBSCRIPTION')
    endpoint = value.get('endpoint')
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        raise ValueError('INVALID_ENDPOINT')
    u = urlsplit(endpoint)
    # Chrome Android FCM only. No arbitrary URLs, ports, redirects or credentials.
    if (u.scheme != 'https' or u.netloc != 'fcm.googleapis.com' or u.query or u.fragment
            or not re.fullmatch(r'/(?:fcm/send|wp)/[A-Za-z0-9_:\-]+', u.path)):
        raise ValueError('UNSUPPORTED_PUSH_PROVIDER')
    public = decode(value['keys'].get('p256dh'), 65)
    EllipticCurvePublicKey.from_encoded_point(SECP256R1(), public)
    decode(value['keys'].get('auth'), 16)
    cleaned = {'endpoint': endpoint, 'keys': {k: value['keys'][k] for k in ('p256dh', 'auth')}}
    return hashlib.sha256(endpoint.encode()).hexdigest(), cleaned


class VerifiedSession(requests.Session):
    def request(self, method, url, **kwargs):
        if urlsplit(url).netloc != 'fcm.googleapis.com' or urlsplit(url).scheme != 'https':
            raise ValueError('PUSH_HOST_REQUIRED')
        kwargs['allow_redirects'], kwargs['verify'] = False, True
        return super().request(method, url, **kwargs)


class PushSender:
    def __init__(self, store, env=None, send=webpush):
        self.store, self.send = store, send
        env = os.environ if env is None else env
        self.presence = {n: bool(env.get(n)) for n in NAMES}
        self.private, self.public, self.subject = (env.get(n, '') for n in NAMES)
        self.ready = False
        self.error = 'VAPID_NOT_CONFIGURED'
        if all(self.presence.values()):
            try:
                key = Vapid.from_string(self.private)
                public = key.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
                if public != decode(self.public, 65) or not re.fullmatch(r'mailto:[^\s@]+@[^\s@]+\.[^\s@]+', self.subject):
                    raise ValueError()
                self.ready, self.error = True, None
            except Exception:
                self.error = 'VAPID_INVALID_CONFIGURATION'

    def config(self):
        return {'ready': self.ready, 'code': self.error, 'variables_present': self.presence,
                'public_key': self.public if self.ready else None, 'provider': 'CHROME_ANDROID_FCM',
                'delivery_confirmed': False}

    def once(self):
        if not self.ready:
            return
        job = self.store.rpc('claim')
        if not job:
            return
        state, code = 'UNKNOWN_SEND_OUTCOME', None
        try:
            _, info = subscription(job['subscription'])
            scenario = job['scenario_id']
            if scenario is not None and not re.fullmatch('[a-f0-9]{64}', scenario):
                raise ValueError('INVALID_SCENARIO')
            payload = json.dumps({'title': 'Aura 5 · '+job['kind'],
                                  'body': 'Новый технический сценарий. NO_EDGE_FOUND · не команда на сделку.' if scenario else 'Тест Web Push. Получение телефоном сервером не подтверждено.',
                                  'scenario_id': scenario, 'event_id': hashlib.sha256(job['id'].encode()).hexdigest()})
            with VerifiedSession() as session:
                response = self.send(subscription_info=info, data=payload,
                                     vapid_private_key=self.private, vapid_claims={'sub': self.subject},
                                     requests_session=session, timeout=8, ttl=60, verbose=False)
            code = response.status_code
            state = 'ACCEPTED_BY_PUSH_SERVICE' if 200 <= code < 300 else 'REJECTED_BY_PUSH_SERVICE'
        except WebPushException as exc:
            if exc.response is not None:
                code = exc.response.status_code
                state = 'REJECTED_BY_PUSH_SERVICE'
        except Exception:
            pass  # Never log subscription URLs, keys, payload exceptions or VAPID secrets.
        self.store.rpc('finish', {'id': job['id'], 'state': state, 'code': code})

    async def run(self):
        while True:
            try:
                await asyncio.to_thread(self.once)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # Durable SENDING claim becomes UNKNOWN_SEND_OUTCOME; never blind resend.
            await asyncio.sleep(2)


def sender(request):
    value = getattr(request.app.state, 'preview_push', None)
    if value is None:
        raise HTTPException(503, 'PUSH_UNAVAILABLE')
    return value


@router.get('/config')
async def config(request: Request):
    return JSONResponse(sender(request).config(), headers={'Cache-Control': 'no-store'})


@router.post('/{action}')
async def mutate(action: str, request: Request):
    if action not in ('subscribe', 'unsubscribe', 'test', 'delivery'):
        raise HTTPException(404)
    if request.headers.get('X-Aura-Push') != 'owner' or request.headers.get('Origin') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'PUSH_SAME_ORIGIN_REQUIRED')
    if 'application/json' not in request.headers.get('Content-Type', ''):
        raise HTTPException(415)
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise HTTPException(413)
    try:
        body = json.loads(raw)
        sid, info = subscription(body['subscription'])
        if action == 'subscribe' and not sender(request).ready:
            raise HTTPException(503, 'VAPID_NOT_CONFIGURED')
        if type(body.get('candidate', False)) is not bool:
            raise ValueError()
        if action == 'test' and not sender(request).ready:
            raise HTTPException(503, 'VAPID_NOT_CONFIGURED')
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, 'INVALID_PUSH_SUBSCRIPTION') from None
    try:
        value = await asyncio.to_thread(sender(request).store.rpc, action,
                                       {'id': sid, 'subscription': info, 'candidate': body.get('candidate', False)})
        return JSONResponse(value, headers={'Cache-Control': 'no-store'})
    except Exception:
        raise HTTPException(503, 'PUSH_STORAGE_UNAVAILABLE') from None
