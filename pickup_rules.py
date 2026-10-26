"""Strict Apple Store allowlist, pickup window, and traffic-aware travel check.

All checkout decisions fail closed. Google Routes API key is read ONLY from
the user's local environment; never committed or put into GitHub Actions.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

PICKUP_DATE = date(2026, 10, 27)
PICKUP_HOURS = (15, 16)  # 3:00 PM, then 4:00 PM, local Boston time.
MAX_DRIVE_MINUTES = 60
# Reserve 5 minutes for ZIP-level origin approximations and changing traffic.
ROUTING_BUFFER_MINUTES = 5
BOSTON = ZoneInfo("America/New_York")
# Store names must match an Apple Store, not fuzzy substring matches.
STORE_ADDRESSES = {
    "The Shops at Blackstone Valley": "70 Worcester-Providence Turnpike, Millbury, MA 01527",
    "Natick": "1245 Worcester Street, Natick, MA 01760",
    "Boylston Street": "815 Boylston Street, Boston, MA 02116",
    "Chestnut Hill": "199 Boylston Street, Chestnut Hill, MA 02467",
    "Legacy Place": "508 Legacy Place, Dedham, MA 02026",
}


class PickupConstraintError(ValueError):
    pass


def canonical_store(store: str) -> str | None:
    value = re.sub(r"[^a-z0-9]+", " ", store.lower()).strip()
    value = re.sub(r"^apple\s+", "", value).strip()
    return next((name for name in STORE_ADDRESSES
                 if value == re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()), None)


def assert_pickup_slot(summary: str, *, require_future: bool = False) -> int:
    """Require the order's pickup summary to show Oct 27 AND precisely 3 or 4 PM."""
    normalized = re.sub(r"\s+", " ", summary).lower()
    if not re.search(r"\b(?:oct(?:ober)?\.?\s+27(?:,?\s+2026)?|10/27(?:/2026)?|2026-10-27)\b", normalized):
        raise PickupConstraintError("Order summary does not verify Tuesday, October 27, 2026")
    if not re.search(r"\b(?:pick\s*up|pickup)\b", normalized):
        raise PickupConstraintError("Not an in-store pickup order")
    # Only exact :00 time starts; 3:30 and 4:30 are NOT accepted.
    matches = re.findall(r"(?<!\d)([34]):00\s*p\.?m\.?(?!\w)", normalized)
    hours = [int(v) + 12 for v in matches if int(v) + 12 in PICKUP_HOURS]
    if not hours:
        raise PickupConstraintError("Order summary must show an exact 3:00 PM or 4:00 PM pickup")
    # During live purchase, do not submit for a pickup time that has passed.
    if require_future:
        now = datetime.now(BOSTON)
        if all(datetime.combine(PICKUP_DATE, time(h, 0), BOSTON) <= now for h in hours):
            raise PickupConstraintError("Requested pickup window has passed")
    return hours[0]


def route_duration_minutes(destination: str, departure: datetime, origin: str | None = None) -> float:
    """Compute traffic-aware route using an optional locally configured Google Routes API key."""
    key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        raise PickupConstraintError("GOOGLE_MAPS_API_KEY not set locally; cannot enforce the one-hour limit")
    if departure <= datetime.now(BOSTON):
        raise PickupConstraintError("Cannot check a past departure")
    origin = (origin or os.getenv("ORIGIN_ADDRESS", "Worcester, MA 01609, USA")).strip()
    if not origin:
        raise PickupConstraintError("Origin is missing")
    body = json.dumps({
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        "departureTime": departure.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://routes.googleapis.com/directions/v2:computeRoutes",
        data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "routes.duration",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            result = json.load(response)
        routes = result.get("routes", [])
        if not isinstance(routes, list) or len(routes) != 1:
            raise PickupConstraintError("Cannot confirm a unique driving route")
        text = routes[0].get("duration", "")
        if not isinstance(text, str) or not re.fullmatch(r"\d+(?:\.\d+)?s", text):
            raise PickupConstraintError("Traffic-aware route duration unavailable")
        return float(text[:-1]) / 60
    except (OSError, ValueError, KeyError) as exc:
        raise PickupConstraintError(f"Driving-time verification failed: {type(exc).__name__}") from exc


def eligible_pickup_hours(store: str, *, now: datetime | None = None) -> dict[int, float]:
    """Returns only pickup hours reachable in <60m with a safety margin; otherwise fails closed."""
    canonical = canonical_store(store)
    if canonical is None:
        raise PickupConstraintError("Store not in the approved five-store list")
    now = now or datetime.now(BOSTON)
    if now.date() > PICKUP_DATE:
        raise PickupConstraintError("October 27 pickup window has expired")
    valid = {}
    for hour in PICKUP_HOURS:
        # Estimate drive departing an hour before each requested pickup.
        departure = datetime.combine(PICKUP_DATE, time(hour - 1, 0), BOSTON)
        if departure <= now:
            continue
        minutes = route_duration_minutes(STORE_ADDRESSES[canonical], departure)
        if minutes <= MAX_DRIVE_MINUTES - ROUTING_BUFFER_MINUTES:
            valid[hour] = minutes
    if not valid:
        raise PickupConstraintError("No 3/4 PM pickup slot is verifiably within the one-hour drive limit")
    return valid
