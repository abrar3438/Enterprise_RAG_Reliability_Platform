"""Per-IP rate limit (sliding window) and a daily request cap. In-process: single worker only."""
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.tables import QueryLog

PER_IP_PER_MINUTE = 10
_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def allow(ip: str) -> bool:
    """True if this IP has made fewer than PER_IP_PER_MINUTE requests in the last 60 seconds."""
    now = time.monotonic()
    with _lock:
        window = _hits[ip]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= PER_IP_PER_MINUTE:
            return False
        window.append(now)
        return True


def daily_limit_reached() -> bool:
    """True if today's query_logs rows (UTC) have reached the daily cap."""
    cap = settings.daily_query_cap
    if cap <= 0:
        return False
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    with SessionLocal() as db:
        count = db.execute(
            select(func.count(QueryLog.id)).where(QueryLog.created_at >= start)
        ).scalar_one()
    return count >= cap