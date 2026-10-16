"""Donation goal API: monthly Ko-fi progress shown beside the footer Ko-fi link.

Ko-fi has no public read API (and its site rejects non-browser clients), so
payments reach Supabase through the kofi-webhook Edge Function and the app
reads the monthly aggregate from the get_donation_progress() RPC.
"""

import json
import logging
import threading
import time
import urllib.error
import urllib.request

from fastapi import APIRouter
from pydantic import BaseModel

from titrack.sync.client import CloudClient

logger = logging.getLogger("titrack")

router = APIRouter(prefix="/api/donations", tags=["donations"])

# Short timeout: this must never hold up the dashboard (see the April Supabase
# outage where an un-timed call blocked startup).
REQUEST_TIMEOUT_SECONDS = 5
CACHE_TTL_SECONDS = 15 * 60
# Retry sooner after a failure (offline at launch, backend not deployed yet)
FAILURE_CACHE_TTL_SECONDS = 60


class DonationProgressResponse(BaseModel):
    """Monthly donation progress. available=False hides the bar."""

    available: bool
    month_total: float = 0.0
    goal: float = 0.0
    currency: str = "USD"


_cache_lock = threading.Lock()
_cached: tuple[float, DonationProgressResponse] | None = None


def _fetch_progress() -> DonationProgressResponse:
    url, key = CloudClient().get_config()
    if not url or not key:
        return DonationProgressResponse(available=False)

    req = urllib.request.Request(
        f"{url}/rest/v1/rpc/get_donation_progress",
        data=b"{}",
        headers={"apikey": key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            rows = json.loads(response.read().decode("utf-8"))
        row = rows[0]
        return DonationProgressResponse(
            available=True,
            month_total=float(row["month_total"]),
            goal=float(row["goal"]),
            currency=row.get("currency") or "USD",
        )
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as e:
        logger.info(f"Donation progress unavailable: {e}")
        return DonationProgressResponse(available=False)


@router.get("/progress", response_model=DonationProgressResponse)
def get_donation_progress() -> DonationProgressResponse:
    """Get this month's donation total and goal (cached; fetched when the app opens)."""
    global _cached
    with _cache_lock:
        now = time.monotonic()
        if _cached is not None:
            fetched_at, progress = _cached
            ttl = CACHE_TTL_SECONDS if progress.available else FAILURE_CACHE_TTL_SECONDS
            if now - fetched_at < ttl:
                return progress
        progress = _fetch_progress()
        _cached = (now, progress)
        return progress
