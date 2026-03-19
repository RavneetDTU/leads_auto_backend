"""
Timezone utilities for the Leads Auto application.
All data is stored in UTC in the database.
This module provides helpers to convert to the display timezone (GMT+2 / SAST).
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

# GMT+2 = South Africa Standard Time (SAST)
SAST = timezone(timedelta(hours=2))


def to_sast(dt: Optional[datetime]) -> Optional[datetime]:
    """
    Convert a naive UTC datetime (as stored in DB) to GMT+2 (SAST).
    Returns None if input is None.
    """
    if dt is None:
        return None
    # If already timezone-aware, convert to SAST
    if dt.tzinfo is not None:
        return dt.astimezone(SAST)
    # Assume naive datetimes are UTC, attach UTC then convert
    return dt.replace(tzinfo=timezone.utc).astimezone(SAST)


def utcnow_sast() -> datetime:
    """Return the current time in GMT+2."""
    return datetime.now(tz=SAST)
