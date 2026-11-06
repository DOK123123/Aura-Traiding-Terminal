"""Optional Web Push transport, not enabled by merely importing this module.

No credentials are generated here. Private keys and subscription endpoints must
never enter diagnostics. Real Android delivery is distinct from HTTP acceptance.
"""
import base64
import hashlib
import json
import re
from urllib.parse import urlsplit

ALLOWED_HOSTS = {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}


def subscription(value):
    if not isinstance(value, dict):
        raise ValueError('INVALID_SUBSCRIPTION')
    endpoint = value.get('endpoint', '')
    if not isinstance(endpoint, str) or len(endpoint) > 4096:
        raise ValueError('INVALID_SUBSCRIPTION')
    url = urlsplit(endpoint)
    if (url.scheme != 'https' or url.hostname not in ALLOWED_HOSTS or url.port not in (None, 443)
            or url.username or url.password or url.fragment or not url.path.startswith('/')):
        raise ValueError('PUSH_DESTINATION_FORBIDDEN')
    keys = value.get('keys', {})
    try:
        for name, size in [('p256dh', 65), ('auth', 16)]:
            raw = keys[name]
            if not isinstance(raw, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}={0,2}', raw):
                raise ValueError()
            decoded = base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4))
            if len(decoded) != size or name == 'p256dh' and decoded[0] != 4:
                raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValueError('INVALID_SUBSCRIPTION_KEYS') from None
    return {'endpoint': endpoint, 'keys': {k: keys[k] for k in ('p256dh', 'auth')}}


def subscription_id(value):
    return hashlib.sha256(subscription(value)['endpoint'].encode()).hexdigest()


class Sender:
    def __init__(self, private_key, public_key, contact, implementation=None):
        # A filename is never accepted as a key; pywebpush must not read files.
        if (not re.fullmatch(r'[A-Za-z0-9_-]{43}', private_key or '')
                or not re.fullmatch(r'[A-Za-z0-9_-]{87}', public_key or '')
                or not isinstance(contact, str) or not re.fullmatch(r'mailto:[^\s@]+@[^\s@]+', contact)):
            raise ValueError('OWNER_VAPID_CONFIGURATION_REQUIRED')
        self._private = private_key
        self.public_key = public_key
        self.contact = contact
        if implementation is None:
            try:
                from pywebpush import webpush
            except ImportError:
                raise ValueError('PUSH_DEPENDENCY_NOT_INSTALLED') from None
            implementation = webpush
        self._send = implementation

    def send(self, target, payload, session):
        """session must be server-owned with redirects disabled (see below)."""
        safe = subscription(target)
        data = json.dumps(payload, separators=(',', ':'))
        if len(data.encode()) > 2500:
            raise ValueError('PUSH_PAYLOAD_LIMIT')
        try:
            response = self._send(subscription_info=safe, data=data,
                                  vapid_private_key=self._private,
                                  vapid_claims={'sub': self.contact}, ttl=60, timeout=5,
                                  requests_session=session)
            code = response.status_code
        except Exception as exc:
            # Never serialize exception text: it can contain an endpoint/key.
            code = getattr(getattr(exc, 'response', None), 'status_code', None)
        return 'ACCEPTED_NOT_DEVICE_CONFIRMED' if code in (200, 201, 202) else 'GONE' if code in (404, 410) else 'RETRY'


def no_redirect_session():
    # Optional dependency only needed when push is actually configured.
    import requests

    class RestrictedSession(requests.Session):
        def request(self, method, url, **kwargs):
            if method.upper() != 'POST':
                raise ValueError('PUSH_METHOD_FORBIDDEN')
            parsed = urlsplit(url)
            if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_HOSTS or parsed.port not in (None, 443):
                raise ValueError('PUSH_DESTINATION_FORBIDDEN')
            kwargs['allow_redirects'] = False
            kwargs['timeout'] = 5
            return super().request(method, url, **kwargs)

    return RestrictedSession()
