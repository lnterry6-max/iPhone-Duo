#!/usr/bin/env python3
"""iPhone Duo 256GB Apple retail pickup stock monitor. Standard library only.

Read-only inventory checking. Optional checkout only on locally armed computers.
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

from pickup_rules import canonical_store, eligible_pickup_hours, PickupConstraintError

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
PURCHASE_LOCK = Path.home() / ".duo-stock-scout" / "purchase-lock.json"


def purchase_lock_reason() -> str | None:
    """Persistent global stop switch; even interrupted/uncertain orders remain locked."""
    if not PURCHASE_LOCK.exists():
        return None
    try:
        status = json.loads(PURCHASE_LOCK.read_text(encoding="utf-8")).get("status", "unknown")
    except (OSError, ValueError):
        status = "unreadable"
    return f"Purchase lock exists ({status}). Monitoring and checkout are stopped; verify Apple Orders before resetting."



def mark_purchased() -> None:
    """Local manual acknowledgment after an accepted Apple order; stops future scans."""
    if PURCHASE_LOCK.exists():
        print("Purchase lock already exists. Stock monitoring is stopped.")
        return
    print("Use this ONLY after Apple has accepted your order (check Orders/email).")
    phrase = input("Type ORDER CONFIRMED to stop all future stock checks: ").strip()
    if phrase != "ORDER CONFIRMED":
        raise ValueError("No purchase marked; monitor remains eligible to run")
    PURCHASE_LOCK.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        PURCHASE_LOCK.parent.chmod(0o700)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(PURCHASE_LOCK, flags, 0o600)
    except FileExistsError:
        print("Purchase lock already exists; monitoring has stopped.")
        return
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"status": "manually_confirmed", "recorded_at": datetime.now(timezone.utc).isoformat()}, f)
        f.write("\n")
    LOG.warning("Apple purchase marked confirmed locally. Watcher will shut down; no more restock opens.")


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
    zip_codes = [z.strip() for z in os.getenv("ZIP_CODES", "01609,01760,02116,02467,02026").split(",") if z.strip()]
    if not zip_codes or any(len(z) != 5 or not z.isascii() or not z.isdecimal() for z in zip_codes):
        raise ValueError("ZIP_CODES must be a comma-separated list of 5-digit U.S. ZIP codes")
    period = float(os.getenv("POLL_SECONDS", "20"))
    if not (15 <= period <= 3600):
        raise ValueError("POLL_SECONDS must be between 15 and 3600 to avoid excessive requests")
    preferred = os.getenv("PREFERRED_COLOR", "Star White").strip()
    if preferred not in ("Star White", "Night Sky"):
        raise ValueError("PREFERRED_COLOR must be Star White or Night Sky")
    checkout_mode = os.getenv("CHECKOUT_MODE", "browser_handoff").strip().lower()
    if checkout_mode not in ("browser_handoff", "chrome_extension", "experimental", "chrome_auto"):
        raise ValueError("CHECKOUT_MODE must be browser_handoff, chrome_extension, chrome_auto, or experimental")
    browser_app = os.getenv("BROWSER_APP", "Safari").strip()
    if browser_app not in ("Safari", "Google Chrome", "Default"):
        raise ValueError("BROWSER_APP must be Safari, Google Chrome, or Default")
    return {
        "checkout_mode": checkout_mode,
        "browser_app": browser_app,
        "zip_codes": list(dict.fromkeys(zip_codes)),
        "period": period,
        "preferred": preferred,
        "state_path": Path(os.getenv("STATE_PATH", ".state/stock.json")),
        "ntfy_topic": os.getenv("NTFY_TOPIC", "").strip(),
        "ntfy_server": os.getenv("NTFY_SERVER", "https://ntfy.sh").strip().rstrip("/"),
        "telegram_token": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
        "open_browser": os.getenv("OPEN_BROWSER", "false").lower() in ("true", "1", "yes"),
        "auto_checkout": checkout_mode in ("experimental", "chrome_auto") and os.getenv("AUTO_CHECKOUT", "false").lower() in ("true", "1", "yes"),
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
    approved_seen = 0
    for store in stores:
        if not isinstance(store, dict):
            continue
        sid = str(store.get("storeNumber") or store.get("storeId") or "").strip()
        sname = str(store.get("storeName") or store.get("name") or sid).strip()
        if not sid or canonical_store(sname) is None:
            continue  # Strict five-store allowlist, even if Apple returned more locations.
        approved_seen += 1
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
    if approved_seen == 0:
        return []  # This ZIP did not return any of the approved Apple Stores.
    if recognized == 0:
        raise InventoryError("No recognizable pickup status for the approved five Apple Stores; check Apple API")
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


def open_checkout_page(url: str, browser_app: str = "Safari") -> bool:
    """Open URL in user's ordinary browser; never read session data or click checkout."""
    if urllib.parse.urlparse(url).hostname != "www.apple.com":
        LOG.error("Refusing browser handoff to a non-Apple URL")
        return False
    if browser_app not in ("Safari", "Google Chrome", "Default"):
        LOG.error("Unrecognized browser selection")
        return False
    try:
        if sys.platform == "darwin":
            command = ["open"]
            if browser_app != "Default":
                command.extend(["-a", browser_app])
            command.append(url)
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            LOG.info("Opening Apple product page in normal %s browser (manual checkout)", browser_app)
            return True
        return webbrowser.open(url)
    except OSError as exc:
        LOG.error("Could not open Apple page: %s", exc)
        return False


def open_in_connected_chrome(url: str, *, cli_path: Path | None = None) -> bool:
    """Open an allowlisted Apple product in the user's *already attached* Chrome.

    Uses the official Playwright CLI Chrome-extension session. No shell,
    screenshots, snapshots, account credentials, cart edits, or payment actions.
    Never runs `open`, which would launch another browser profile.
    """
    if url not in BUY_URLS.values():
        LOG.error("Chrome handoff refused: not an approved 256GB Apple product URL")
        return False
    if sys.platform != "darwin" or os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        LOG.error("Connected Chrome handoff only supported on the local Mac")
        return False
    binary = cli_path or Path.home() / ".local" / "bin" / "playwright-cli"
    if not binary.is_file():
        LOG.warning("Playwright CLI not installed at %s", binary)
        return False
    try:
        result = subprocess.run(
            [str(binary), "-s=chrome", "tab-new", url],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        LOG.warning("Chrome extension handoff unavailable (%s)", type(exc).__name__)
        return False
    if result.returncode != 0:
        # Do not log CLI output: it may include tab names or private URLs.
        LOG.warning("Connected Chrome session unavailable; reattach with: playwright-cli attach --extension=chrome")
        return False
    LOG.info("Opened approved 256GB Apple product in attached Chrome; checkout remains manual")
    return True


def open_from_config(url: str, config: dict[str, Any]) -> bool:
    """Try connected Chrome if chosen; safely fall back to ordinary Chrome."""
    if config.get("checkout_mode") in ("chrome_extension", "chrome_auto"):
        if open_in_connected_chrome(url):
            return True
        LOG.warning("Chrome session not attached; opening the product URL in ordinary Chrome")
        return open_checkout_page(url, "Google Chrome")
    return open_checkout_page(url, config.get("browser_app", "Safari"))


def launch_checkout_bot(stock: Stock, config: dict[str, Any]) -> bool:
    """Only local, opt-in checkout attempts; never from GitHub-hosted runners."""
    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        LOG.error("Automatic checkout disabled in GitHub Actions")
        return False
    script = Path(__file__).resolve().with_name("checkout_bot.py")
    if not script.exists():
        LOG.error("checkout_bot.py missing; checkout not started")
        return False
    try:
        state_dir = Path(config["state_path"]).parent
        state_dir.mkdir(parents=True, exist_ok=True)
        command = "attempt-chrome" if config.get("checkout_mode") == "chrome_auto" else "attempt"
        with (state_dir / "checkout-bot.log").open("a", encoding="utf-8") as log:
            subprocess.Popen([sys.executable, str(script), command, "--sku", stock.sku,
                              "--store-id", stock.store_id, "--store-name", stock.store,
                              "--zip-code", stock.zip_code], stdin=subprocess.DEVNULL,
                             stdout=log, stderr=log, start_new_session=True, cwd=str(script.parent))
        return True
    except OSError as exc:
        LOG.error("Checkout process could not start: %s", exc)
        return False


def check(config: dict[str, Any], *, send: bool = True) -> bool:
    """Run a round. Returns true when Apple responded validly to every configured ZIP."""
    reason = purchase_lock_reason()
    if reason:
        LOG.warning("%s", reason)
        return True
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
        # Only the five selected stores, with an authorized future pickup hour.
        # No route API is used: travel time is NOT verified.
        candidates = preferred_first(
            [item for item in new if canonical_store(item.store) is not None],
            config["preferred"],
        )
        eligible = []
        for candidate in candidates:
            try:
                hours = eligible_pickup_hours(candidate.store)
                eligible.append(candidate)
                LOG.info("Approved store: %s; allowed future pickup hours: %s (drive time unverified)",
                         candidate.store, ", ".join(f"{hour-12}:00 PM" for hour in hours))
            except PickupConstraintError as exc:
                LOG.info("Ignored store %s: %s", candidate.store, exc)
        # Keep new matches available for future recheck if their time constraint is unconfirmed.
        for item in candidates:
            if item not in eligible:
                updated.pop(item.key, None)
        if not eligible:
            state["status"] = updated
            state["last_check_utc"] = datetime.now(timezone.utc).isoformat()
            write_state(config["state_path"], state)
            return not errors
        new = eligible
        top = new[0]
        buy_url = BUY_URLS[top.sku]
        lines = [f"{s.label} | {s.store} ({s.store_id})" for s in new[:8]]
        message = "Apple pickup stock detected near ZIP " + ",".join(config["zip_codes"]) + ":\n" + "\n".join(lines)
        if len(new) > 8:
            message += f"\n...and {len(new) - 8} more matches"
        message += "\nCheck that Apple offers Oct 27 pickup at 3:00 or 4:00 PM. Store is on your allowlist; drive time NOT verified."
        LOG.warning("NEW STOCK: %s", message.replace("\n", " | "))
        delivered = send_alert(message, "iPhone Duo 256GB IN STOCK", buy_url, config)
        initiated = False
        if config.get("checkout_mode") in ("experimental", "chrome_auto") and config.get("auto_checkout"):
            initiated = launch_checkout_bot(top, config)
        opened = False
        if config["open_browser"] and not initiated:
            opened = open_from_config(buy_url, config)
        if delivered or opened or initiated:
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
    parser.add_argument("command", nargs="?", choices=["watch", "once", "test-alert", "prepare-checkout", "mark-purchased"], default="once")
    parser.add_argument("--env", default=".env", help="Read local .env file (never commit secrets)")
    parser.add_argument("--no-notify", action="store_true", help="Do stock lookup without sending notifications")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    load_env(Path(args.env))
    try:
        if args.command == "mark-purchased":
            mark_purchased()
            return 0
        config = get_config()
        if args.command == "prepare-checkout":
            LOG.info("Opening Apple Store for safe browser handoff (mode %s).", config["checkout_mode"])
            LOG.info("No order is placed; use Apple checkout directly in your browser.")
            return 0 if open_from_config(BUY_URLS["MK1E4LL/A"], config) else 1
        if args.command == "test-alert":
            good = send_alert("This is a test alert, NOT actual inventory. Checkout is always manual.",
                              "Duo monitor test", BUY_URLS["MK1E4LL/A"], config)
            return 0 if good else 2
        if args.command == "once":
            return 0 if check(config, send=not args.no_notify) else 1
        # Multiple ZIPs mean multiple Apple requests per round.
        # Don't run an extremely aggressive unattended polling loop.
        if config["period"] < 120:
            LOG.warning("POLL_SECONDS=%g is too aggressive for five ZIP queries; using 120 seconds in watch mode.", config["period"])
            config["period"] = 120
        LOG.info("Starting Apple pickup monitor: %s; 256GB only; every ~%gs; preferred %s",
                 ",".join(config["zip_codes"]), config["period"], config["preferred"])
        errors_in_row = 0
        while True:
            reason = purchase_lock_reason()
            if reason:
                LOG.warning("%s", reason)
                LOG.warning("Exiting watcher; no additional purchase attempts.")
                break
            try:
                if check(config, send=not args.no_notify):
                    errors_in_row = 0
                else:
                    errors_in_row += 1
            except Exception:  # daemon must survive unexpected errors; don't misreport in-stock
                errors_in_row += 1
                LOG.exception("Unexpected monitor error; retrying")
            # Circuit breaker: a blocked/unhealthy service is not sold out.
            # Stop instead of indefinitely retrying a server that is refusing us.
            if errors_in_row >= 3:
                LOG.error("Three consecutive failed inventory rounds. Stopping to respect Apple's response.")
                LOG.error("Availability is UNKNOWN, not sold out. Review network/site status before manually restarting.")
                return 2
            # Back off on errors; do not retry aggressively after Apple refuses access.
            backoff = min(1200.0, max(config["period"], 180) * (2 ** min(errors_in_row, 5))) if errors_in_row else config["period"]
            delay = max(15, backoff + random.uniform(-2, 2))
            if errors_in_row:
                LOG.warning("Check errors=%d; waiting %.1f seconds before retry", errors_in_row, delay)
            # Stop as soon as an order attempt creates its permanent purchase lock.
            remaining = delay
            while remaining > 0:
                if purchase_lock_reason():
                    LOG.warning("Purchase lock detected. Shutting down watcher immediately.")
                    return 0
                tick = min(1.0, remaining)
                time.sleep(tick)
                remaining -= tick
    except KeyboardInterrupt:
        LOG.info("Stopped by user")
        return 0
    except (ValueError, RuntimeError) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
