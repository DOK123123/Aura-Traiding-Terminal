"""Authenticated scheduler attribution, never an authorization or execution gate."""
from contextvars import ContextVar
import re
from fastapi import HTTPException, Request
from app.paper.api import HEADERS

scheduled_delivery = ContextVar('active43_scheduled_delivery', default=None)


def attribution(request: Request, now: float) -> dict | None:
    values = request.headers.getlist('X-Aura-Scheduled-At')
    if not values:
        return None  # Old Worker and manual clients remain compatible, unverified.
    ids = request.headers.getlist('X-Aura-Invocation-Id')
    if (len(values) != 1 or not re.fullmatch(r'[0-9]{13}', values[0])
            or len(ids) != 1 or not re.fullmatch('[a-f0-9]{32}', ids[0])):
        raise HTTPException(400, 'INVALID_SCHEDULE_ATTRIBUTION', headers=HEADERS)
    at = int(values[0])
    # Cloudflare scheduledTime may include delivery jitter within the cron minute/slot.
    # Preserve the 5-minute cron slot (minute 2, 7, 12, ...) and freshness bound.
    if not 120000 <= at % 300000 < 300000 or not -3000 <= now * 1000 - at <= 270000:
        raise HTTPException(400, 'INVALID_SCHEDULE_ATTRIBUTION', headers=HEADERS)
    return dict(source='CLOUDFLARE_SCHEDULED_REPORTED', scheduled_at=at // 1000,
                invocation_id=ids[0])
