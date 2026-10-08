"""In-process answer cache with TTL and a size cap. Single-process only (no Redis in v1)."""
import hashlib
import json
import re
import threading
import time
from collections import OrderedDict

from app.core.config import settings
from app.services.generation import PROMPT_VERSION

# Bump this whenever the corpus changes (re-ingest, chunker or cleaning change)
CORPUS_VERSION = "sec-10k-13filings-10628chunks-v1"
TTL_ANSWER_S = 24 * 3600
TTL_REFUSAL_S = 1 * 3600
MAX_ENTRIES = 500

_lock = threading.Lock()
_store: "OrderedDict[str, tuple[float, dict]]" = OrderedDict()
_counts = {"hits": 0, "misses": 0}


def normalize_question(question: str) -> str:
    return re.sub(r"\s+", " ", (question or "")).strip().lower()


def make_key(question: str, ticker: str | None) -> str:
    raw = json.dumps({
        "q": normalize_question(question),
        "t": (ticker or "").upper(),
        "p": PROMPT_VERSION,
        "m": settings.craftx_model,
        "c": CORPUS_VERSION,
    }, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cacheable(result: dict) -> bool:
    """Only complete, verified-or-skipped answers. Never errors, truncation or unclear verdicts."""
    return (
        not result.get("error")
        and result.get("finish_reason") == "stop"
        and bool(result.get("answer"))
        and result.get("verification") != "inconclusive"
    )


def get(key: str) -> dict | None:
    now = time.monotonic()
    with _lock:
        item = _store.get(key)
        if item is None:
            _counts["misses"] += 1
            return None
        expires, value = item
        if expires < now:
            del _store[key]
            _counts["misses"] += 1
            return None
        _store.move_to_end(key)
        _counts["hits"] += 1
        return dict(value)


def put(key: str, result: dict) -> None:
    ttl = TTL_REFUSAL_S if result.get("refused") else TTL_ANSWER_S
    with _lock:
        _store[key] = (time.monotonic() + ttl, dict(result))
        _store.move_to_end(key)
        while len(_store) > MAX_ENTRIES:
            _store.popitem(last=False)


def stats() -> dict:
    with _lock:
        return {**_counts, "entries": len(_store)}