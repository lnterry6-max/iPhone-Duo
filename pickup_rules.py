"""Approved Apple Stores and strict Tuesday, October 27, 2026 pickup slots.

No mapping API, API key, geolocation, or verified drive-time service is used.
The user's five-store allowlist replaces the earlier live driving-time rule.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

BOSTON = ZoneInfo("America/New_York")
PICKUP_DATE = date(2026, 10, 27)
PICKUP_HOURS = (15, 16)  # 3:00 PM or 4:00 PM, Eastern time

# Exact Apple Store names. An Apple pickup feed may include other stores:
# those stores must never trigger a notification or checkout.
STORE_ADDRESSES = {
    "The Shops at Blackstone Valley": "70 Worcester-Providence Turnpike, Millbury, MA 01527",
    "Natick": "1245 Worcester Street, Natick, MA 01760",
    "Boylston Street": "815 Boylston Street, Boston, MA 02116",
    "Chestnut Hill": "199 Boylston Street, Chestnut Hill, MA 02467",
    "Legacy Place": "508 Legacy Place, Dedham, MA 02026",
}


class PickupConstraintError(ValueError):
    """The selected store/date/time is outside the authorized constraints."""


def canonical_store(store: str) -> str | None:
    """Match only one of the five named stores; an optional 'Apple' prefix is OK."""
    normalized = re.sub(r"[^a-z0-9]+", " ", store.casefold()).strip()
    normalized = re.sub(r"^apple\s+", "", normalized).strip()
    for name in STORE_ADDRESSES:
        expected = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
        if normalized == expected:
            return name
    return None


def eligible_pickup_hours(store: str, *, now: datetime | None = None) -> dict[int, bool]:
    """Allowed future hours for an approved store, without any routing API.

    This ONLY enforces the five-store list and clock time. It does not prove
    that a drive from Worcester can be completed in an hour.
    """
    if canonical_store(store) is None:
        raise PickupConstraintError("Store is not one of the five approved Apple Stores")
    now = now or datetime.now(BOSTON)
    if now.tzinfo is None:
        raise PickupConstraintError("Now must be timezone-aware")
    now = now.astimezone(BOSTON)
    result = {
        hour: True
        for hour in PICKUP_HOURS
        if datetime.combine(PICKUP_DATE, time(hour, 0), BOSTON) > now
    }
    if not result:
        raise PickupConstraintError("The October 27 pickup window has passed")
    return result


def assert_pickup_slot(summary: str, *, require_future: bool = False) -> int:
    """Require pickup on October 27, 2026 at exactly 3 or 4 PM, never shipping."""
    normalized = re.sub(r"\s+", " ", summary).casefold()
    if not re.search(
        r"\b(?:oct(?:ober)?\.?\s+27(?:,?\s+2026)?|10/27(?:/2026)?|2026-10-27)\b",
        normalized,
    ):
        raise PickupConstraintError("Final summary must show Tuesday, October 27, 2026")
    if not re.search(r"\b(?:pick\s*up|pickup)\b", normalized):
        raise PickupConstraintError("Final summary does not show in-store pickup")
    matches = re.findall(r"(?<!\d)([34]):00\s*p\.?m\.?(?!\w)", normalized)
    hours = [int(hour) + 12 for hour in matches if int(hour) + 12 in PICKUP_HOURS]
    if not hours:
        raise PickupConstraintError("Final summary must show exactly 3:00 PM or 4:00 PM")
    if require_future:
        now = datetime.now(BOSTON)
        hours = [
            hour for hour in hours
            if datetime.combine(PICKUP_DATE, time(hour, 0), BOSTON) > now
        ]
        if not hours:
            raise PickupConstraintError("Requested pickup time is already past")
    return hours[0]
