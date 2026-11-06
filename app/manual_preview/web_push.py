"""Optional Web Push transport, not enabled by merely importing this module.

No credentials are generated here. Private keys and subscription endpoints must
never enter diagnostics. Real Android delivery is distinct from HTTP acceptance.
"""
import base64
import hashlib
import json
import re
from urllib.parse import urlsplit
from typing import Callable

ALLOWED_HOSTS = {'fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}


def subscription(value: dict) -> dict:
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
            if name == 'p256dh':
                from cryptography.hazmat.primitives.asymmetric import ec
                ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(),decoded)
    except (ValueError, KeyError, TypeError):
        raise ValueError('INVALID_SUBSCRIPTION_KEYS') from None
    return {'endpoint': endpoint, 'keys': {k: keys[k] for k in ('p256dh', 'auth')}}


def subscription_id(value: dict) -> str:
    return hashlib.sha256(subscription(value)['endpoint'].encode()).hexdigest()


class Sender:
    def __init__(self, private_key: str, public_key: str, contact: str,
                 implementation: Callable | None = None) -> None:
        # A filename is never accepted as a key; pywebpush must not read files.
        if (not isinstance(private_key, str) or not isinstance(public_key, str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{43}', private_key or '')
                or not re.fullmatch(r'[A-Za-z0-9_-]{87}', public_key or '')
                or not isinstance(contact, str) or not (re.fullmatch(r'mailto:[^\s@]+@[^\s@]+', contact)
                or contact == 'https://aura-manual-trader5-isolated-preview.onrender.com')):
            raise ValueError('OWNER_VAPID_CONFIGURATION_REQUIRED')
        self._private = private_key
        self.public_key = public_key
        self.contact = contact
        if implementation is None:
            try:
                from pywebpush import webpush
                from py_vapid import Vapid
                from cryptography.hazmat.primitives import serialization
            except ImportError:
                raise ValueError('PUSH_DEPENDENCY_NOT_INSTALLED') from None
            # Pass a parsed key object: pywebpush must never interpret the key
            # string as a local filename. Verify the advertised public key too.
            parsed = Vapid.from_string(private_key)
            actual = parsed.public_key.public_bytes(serialization.Encoding.X962,
                                                    serialization.PublicFormat.UncompressedPoint)
            if base64.urlsafe_b64encode(actual).decode().rstrip('=') != public_key:
                raise ValueError('VAPID_KEY_PAIR_MISMATCH')
            self._private = parsed
            implementation = webpush
        self._send = implementation

    def send(self, target: dict, payload: dict, session: object) -> str:
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


def no_redirect_session() -> object:
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


def generate_vapid() -> dict:
    """Generate once on the server; the caller persists it privately with CAS.

    Never use environment defaults, dummy fixtures or an ephemeral key file.
    Nothing generated by this function is logged or returned to a browser.
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization
    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, 'big')
    public = key.public_key().public_bytes(serialization.Encoding.X962,
                                           serialization.PublicFormat.UncompressedPoint)
    encode = lambda value: base64.urlsafe_b64encode(value).decode('ascii').rstrip('=')
    return {'private': encode(private), 'public': encode(public),
            'contact': 'https://aura-manual-trader5-isolated-preview.onrender.com'}
