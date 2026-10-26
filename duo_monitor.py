#!/usr/bin/env python3
"""iPhone Duo 256GB Apple retail pickup stock monitor. Standard library only.

Read-only inventory checking. Does not add items to a bag or submit purchases.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

API = "https://www.apple.com/shop/retail/pickup-message"
BUY_URLS = {
    "MK1E4LL/A": "https://www.apple.com/shop/buy-iphone/iphone-duo/7.6-inch-display-256gb-star-white-unlocked",
    "MK1F4LL/A": "https://www.apple.com/shop/buy-iphone/iphone-duo/7.6-inch-display-256gb-night-sky-unlocked",
}
# U.S. Apple 256GB SKUs only. Deliberately not configurable to avoid accidental wrong-capacity purchases.
PRODUCTS = {
    "MK1E4LL/A": "Star White — 256GB",
    "MK1F4LL/A": "Night Sky — 256GB",
}
LOG = logging.getLogger("duo_stock_scout")


class InventoryError(Exception):
    """Network, format, or availability API failure (never assume out of stock)."""


@dataclass(frozen=True)
class Stock:
    store: str
    store_id: str
    sku: str
    label: str
    status: str     # in_stock | out_of_stock | unknown
    zip_code: str

    @property
    def key(self) -> str:
        return f"{self.store_id}|{self.sku}"


def load_env(path: Path) -> None:
    """Simple local .env reader. No command evaluation or shell execution."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line or raw_line.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value[:1] in ("'", '"') and value[-1:] == value[:1]:
            value = value[1:-1]
        if key.isidentifier():
            os.environ.setdefault(key, value)


def get_config() -> dict[str, Any]:
    zip_codes = [z.strip() for z in os.getenv("ZIP_CODES", "01609").split(",") if z.strip()]
    if not zip_codes or any(len(z) != 5 or not z.isascii() or not z.isdecimal() for z in zip_codes):
        raise ValueError("ZIP_CODES must be a comma-separated list of 5-digit U.S. ZIP codes")
    period = float(os.getenv("POLL_SECONDS", "20"))
    if not (15 <= period <= 3600):
        raise ValueError("POLL_SECONDS must be between 15 and 3600 to avoid excessive requests")
    preferred = os.getenv("PREFERRED_COLOR", "Star White").strip()
    if preferred not in ("Star White", "Night Sky"):
        raise ValueError("PREFERRED_COLOR must be Star White or Night Sky")
    return {
        "zip_codes": list(dict.fromkeys(zip_codes)),
        "period": period,
        "preferred": preferred,
        "state_path": Path(os.getenv("STATE_PATH", ".state/stock.json")),
        "ntfy_topic": os.getenv("NTFY_TOPIC", "").strip(),
        "ntfy_server": os.getenv("NTFY_SERVER", "https://ntfy.sh").strip().rstrip("/"),
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "open_browser": os.getenv("OPEN_BROWSER", "false").lower() in ("true", "1", "yes"),
    }


def stock_url(zip_code: str) -> str:
    parts = [(f"parts.{i}", sku) for i, sku in enumerate(PRODUCTS)]
    return API + "?" + urllib.parse.urlencode([("pl", "true"), ("location", zip_code), *parts])


def fetch_inventory(zip_code: str) -> dict[str, Any]:
    request = urllib.request.Request(stock_url(zip_code), headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read(3_000_000).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429, 541):
            raise InventoryError(f"Apple refused the request (HTTP {exc.code}); slow down or try a local connection") from exc
        raise InventoryError(f"Apple responded HTTP {exc.code}") from exc
    except (OSError, TimeoutError, ValueError, UnicodeError) as exc:
        raise InventoryError(f"Apple pickup request failed: {type(exc).__name__}: {exc}") from exc


def parse_inventory(payload: dict[str, Any], zip_code: str) -> list[Stock]:
    """Read both known Apple response shapes; never classify malformed data as sold out."""
    if not isinstance(payload, dict):
        raise InventoryError("Expected a JSON object")
    body = payload.get("body")
    if not isinstance(body, dict):
        raise InventoryError("No body object in Apple response")
    stores = body.get("stores")
    if stores is None:
        stores = (body.get("content") or {}).get("pickupMessage", {}).get("stores")
    if not isinstance(stores, list) or not stores:
        raise InventoryError("No nearby stores in Apple response (could be an API change)")
    output = []
    recognized = 0
    for store in stores:
        if not isinstance(store, dict):
            continue
        sid = str(store.get("storeNumber") or store.get("storeId") or "").strip()
        sname = str(store.get("storeName") or store.get("name") or sid).strip()
        if not sid:
            continue
        pa = store.get("partsAvailability")
        if not isinstance(pa, dict):
            continue
        for sku, label in PRODUCTS.items():
            entry = pa.get(sku)
            if not isinstance(entry, dict):
                continue
            raw = str(entry.get("pickupDisplay") or "").strip().lower()
            if raw == "available":
                status = "in_stock"
                recognized += 1
            elif raw == "unavailable":
                status = "out_of_stock"
                recognized += 1
            else:
                status = "unknown"
            output.append(Stock(sname, sid, sku, label, status, zip_code))
    if recognized == 0:
        raise InventoryError("No recognizable pickup states for either 256GB SKU; check Apple product IDs/API")
    return output


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": {}, "last_failure_alert": 0}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw.get("status"), dict):
            raise ValueError("state file lacks status mapping")
        return raw
    except (ValueError, OSError) as exc:
        raise RuntimeError(f"Cannot safely load {path}: {exc}") from exc


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def compute_new_stock(items: list[Stock], existing: dict[str, Any]) -> tuple[list[Stock], dict[str, Any]]:
    """Alert on newly available; preserve last status if an API response is missing/unknown."""
    statuses = dict(existing)
    new = []
    for item in items:
        if item.status == "unknown":
            continue
        if item.status == "in_stock" and statuses.get(item.key) != "in_stock":
            new.append(item)
        statuses[item.key] = item.status
    return new, statuses


def preferred_first(items: list[Stock], preferred: str) -> list[Stock]:
    return sorted(items, key=lambda s: (not s.label.startswith(preferred), s.store.lower()))


def post(url: str, body: bytes, headers: dict[str, str]) -> None:
    request = urllib.request.Request(url, data=body, method="POST", headers=headers)
    with urllib.request.urlopen(request, timeout=12) as response:
        if not (200 <= response.status < 300):
            raise OSError(f"Notifier HTTP {response.status}")


def send_alert(message: str, title: str, url: str, config: dict[str, Any]) -> bool:
    """Return true if at least one alert channel succeeded."""
    successful = False
    if config["ntfy_topic"]:
        topic = urllib.parse.quote(config["ntfy_topic"], safe="")
        try:
            post(f'{config["ntfy_server"]}/{topic}', message.encode("utf-8"), {
                "Title": title.encode("ascii", errors="ignore").decode("ascii") or "Duo stock found",
                "Priority": "urgent",
                "Tags": "iphone,rotating_light",
                "Click": url,
            })
            LOG.info("ntfy alert sent")
            successful = True
        except (OSError, urllib.error.URLError) as exc:
            LOG.error("ntfy alert failed: %s", exc)
    if config["telegram_token"] and config["telegram_chat_id"]:
        endpoint = f'https://api.telegram.org/bot{config["telegram_token"]}/sendMessage'
        body = urllib.parse.urlencode({
            "chat_id": config["telegram_chat_id"],
            "text": title + "\n" + message + "\n" + url,
            "disable_web_page_preview": "true",
        }).encode()
        try:
            post(endpoint, body, {"Content-Type": "application/x-www-form-urlencoded"})
            LOG.info("Telegram alert sent")
            successful = True
        except (OSError, urllib.error.URLError) as exc:
            LOG.error("Telegram alert failed (check credentials and chat ID): %s", type(exc).__name__)
    if not (config["ntfy_topic"] or config["telegram_chat_id"]):
        LOG.warning("No alert destination configured. Set NTFY_TOPIC or Telegram credentials.")
    return successful


def open_checkout_page(url: str) -> None:
    """Open a product page for manual purchase on a Mac; never auto-submit payment."""
    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            LOG.warning("Unable to open browser: %s", exc)


def check(config: dict[str, Any], *, send: bool = True) -> bool:
    """Run a round. Returns true when Apple responded validly to every configured ZIP."""
    all_items = []
    errors = []
    for zip_code in config["zip_codes"]:
        try:
            items = parse_inventory(fetch_inventory(zip_code), zip_code)
            all_items.extend(items)
        except InventoryError as exc:
            errors.append(f"{zip_code}: {exc}")
            LOG.error("%s", errors[-1])
    if not all_items:
        LOG.error("No valid inventory received; NOT assuming sold out")
        return False
    by_key = {item.key: item for item in all_items}
    all_items = list(by_key.values())
    counts = {status: sum(s.status == status for s in all_items) for status in ("in_stock", "out_of_stock", "unknown")}
    LOG.info("checked %d nearby stores (%s) — available=%d unavailable=%d unknown=%d",
             len(set(s.store_id for s in all_items)), ",".join(config["zip_codes"]),
             counts["in_stock"], counts["out_of_stock"], counts["unknown"])
    for item in preferred_first([s for s in all_items if s.status == "in_stock"], config["preferred"]):
        LOG.warning("IN STOCK: %s | Apple %s (%s) | from ZIP %s", item.label, item.store, item.store_id, item.zip_code)
    # Read-only lookups should not consume an alert by recording a new in-stock state.
    if not send:
        return not errors
    state = read_state(config["state_path"])
    new, updated = compute_new_stock(all_items, state["status"])
    # If notifications fail, do not forget the new matches; retry on next poll.
    if new:
        new = preferred_first(new, config["preferred"])
        top = new[0]
        buy_url = BUY_URLS[top.sku]
        lines = [f"{s.label} | {s.store} ({s.store_id})" for s in new[:8]]
        message = "Apple pickup stock detected near ZIP " + ",".join(config["zip_codes"]) + ":\n" + "\n".join(lines)
        if len(new) > 8:
            message += f"\n...and {len(new) - 8} more matches"
        message += "\nTap to order the correct 256GB variant. Complete checkout yourself."
        LOG.warning("NEW STOCK: %s", message.replace("\n", " | "))
        delivered = send_alert(message, "iPhone Duo 256GB IN STOCK", buy_url, config)
        if config["open_browser"]:
            open_checkout_page(buy_url)
        if delivered or config["open_browser"]:
            state["status"] = updated
        else:
            for s in new:
                updated.pop(s.key, None)
            state["status"] = updated
            LOG.warning("Notification not confirmed; will retry alerts next poll")
    else:
        state["status"] = updated
    state["last_check_utc"] = datetime.now(timezone.utc).isoformat()
    write_state(config["state_path"], state)
    if errors:
        LOG.warning("Partial success, ZIP errors: %s", "; ".join(errors))
    return not errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor iPhone Duo 256GB pickup availability near ZIP 01609")
    parser.add_argument("command", nargs="?", choices=["watch", "once", "test-alert", "prepare-checkout"], default="once")
    parser.add_argument("--env", default=".env", help="Read local .env file (never commit secrets)")
    parser.add_argument("--no-notify", action="store_true", help="Do stock lookup without sending notifications")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    load_env(Path(args.env))
    try:
        config = get_config()
        if args.command == "prepare-checkout":
            LOG.info("Opening Apple Store in your default browser. Sign in directly with Apple yourself.")
            LOG.info("Never enter Apple passwords, verification codes or payment information in this app or GitHub.")
            return 0 if webbrowser.open(BUY_URLS["MK1E4LL/A"]) else 1
        if args.command == "test-alert":
            good = send_alert("This is a test alert, NOT actual inventory. Checkout is always manual.",
                              "Duo monitor test", BUY_URLS["MK1E4LL/A"], config)
            return 0 if good else 2
        if args.command == "once":
            return 0 if check(config, send=not args.no_notify) else 1
        LOG.info("Starting Apple pickup monitor: %s; 256GB only; every ~%gs; preferred %s",
                 ",".join(config["zip_codes"]), config["period"], config["preferred"])
        errors_in_row = 0
        while True:
            try:
                if check(config, send=not args.no_notify):
                    errors_in_row = 0
                else:
                    errors_in_row += 1
            except Exception:  # daemon must survive unexpected errors; don't misreport in-stock
                errors_in_row += 1
                LOG.exception("Unexpected monitor error; retrying")
            # Back off on errors to avoid hammering Apple when blocked or API changes.
            backoff = min(600.0, config["period"] * (2 ** min(errors_in_row, 5))) if errors_in_row else config["period"]
            delay = max(15, backoff + random.uniform(-2, 2))
            if errors_in_row:
                LOG.warning("Check errors=%d; waiting %.1f seconds before retry", errors_in_row, delay)
            time.sleep(delay)
    except KeyboardInterrupt:
        LOG.info("Stopped by user")
        return 0
    except (ValueError, RuntimeError) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
