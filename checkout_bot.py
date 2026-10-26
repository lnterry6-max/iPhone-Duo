#!/usr/bin/env python3
"""Local Apple Store checkout experiment. Never stores account passwords.

Apple's checkout DOM is not a supported API, so automation can stop on a changed
page. The bot fails closed instead of clicking unfamiliar payment controls.
"""
from __future__ import annotations

import argparse
import json
import fcntl
import logging
import os
from pathlib import Path
import re
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from duo_monitor import BUY_URLS, PRODUCTS, fetch_inventory, parse_inventory, InventoryError, get_config, send_alert, load_env
from pickup_rules import assert_pickup_slot, canonical_store, eligible_pickup_hours, PickupConstraintError

LOG = logging.getLogger("duo_checkout")
PROFILE = Path.home() / ".duo-stock-scout" / "apple-browser"
AUTH = Path.home() / ".duo-stock-scout" / "authorization.json"
LOCK = Path.home() / ".duo-stock-scout" / "checkout.lock"
PURCHASE_LOCK = Path.home() / ".duo-stock-scout" / "purchase-lock.json"
ALLOWED_SKUS = frozenset(PRODUCTS)


class CheckoutError(RuntimeError):
    pass


def secure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "posix":
        path.chmod(0o700)


def atomic_json(path: Path, data: dict) -> None:
    secure_directory(path.parent)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        os.chmod(tmp, 0o600)
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    tmp.replace(path)


def read_auth(path: Path = AUTH) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError) as exc:
        raise CheckoutError("Not armed. Run 'python3 checkout_bot.py arm'.") from exc


def validate_auth(auth: dict, sku: str, now: float | None = None) -> None:
    now = now or time.time()
    if sku not in ALLOWED_SKUS:
        raise CheckoutError("Only the approved 256GB Duo models may be purchased")
    if auth.get("status") != "armed":
        raise CheckoutError("Authorization already used or revoked. No second attempt.")
    if now >= float(auth.get("expires_at", 0)):
        raise CheckoutError("Purchase authorization expired")
    amount = float(auth.get("max_total_usd", 0))
    if not (1999 <= amount <= 3000):
        raise CheckoutError("Purchase limit must be between $1999 and $3000")
    if auth.get("quantity") != 1:
        raise CheckoutError("Only one device is authorized")
    if auth.get("allow_submit") is not True:
        raise CheckoutError("Automatic order submission is not armed")


def arm(args: argparse.Namespace) -> None:
    if PURCHASE_LOCK.exists():
        raise CheckoutError("A checkout was already attempted. Check Apple orders first; the purchase lock must be explicitly reset.")
    if not (1999 <= args.max_total <= 3000):
        raise CheckoutError("Set a dollar maximum between $1999 and $3000 (including tax)")
    if not (0 < args.hours <= 24):
        raise CheckoutError("Authorization expires within 24 hours")
    print("This authorizes ONE real Apple order for a 256GB iPhone Duo.")
    print("Allowed colors: Star White or Night Sky; allowed quantity: one.")
    print(f"Maximum total price including tax: ${args.max_total:.2f}.")
    print("If Apple changes the page or requests verification, checkout will stop.")
    if input("To authorize an automatic charge, type BUY ONE DUO: ").strip() != "BUY ONE DUO":
        raise CheckoutError("Not armed; confirmation phrase did not match")
    atomic_json(AUTH, {
        "status": "armed", "expires_at": time.time() + 3600 * args.hours,
        "max_total_usd": args.max_total, "quantity": 1,
        "allow_submit": True, "armed_at": datetime.now(timezone.utc).isoformat(),
    })
    print(f"Armed for {args.hours:g} hours. Remove authorization with 'python3 checkout_bot.py disarm'.")


def get_playwright():
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError as exc:
        raise CheckoutError("Install local checkout requirements: pip install -r requirements-checkout.txt; python3 -m playwright install chromium") from exc
    return sync_playwright, PlaywrightTimeoutError


def ensure_apple(url: str) -> None:
    host = urlparse(url).hostname or ""
    if host != "www.apple.com" and not host.endswith(".apple.com"):
        raise CheckoutError(f"Refusing to automate non-Apple website: {host}")


def browser_context(playwright):
    secure_directory(PROFILE)
    return playwright.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE), headless=False, accept_downloads=False,
        viewport={"width": 1150, "height": 850},
    )


def login() -> None:
    print("Sign in ONLY on apple.com within the opened browser window.")
    print("Apple handles your password, passkey, and 2FA; this script never asks for them.")
    print("Set your preferred pickup/payment details in Apple, and ensure your bag is empty.")
    sync_playwright, _ = get_playwright()
    with sync_playwright() as p:
        context = browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.apple.com/shop/account/home", wait_until="domcontentloaded", timeout=30000)
        input("After signing in and checking your bag, return here and press Enter to close: ")
        context.close()
    print("Browser session saved locally in your home directory. Keep it private.")


def verify_stock(sku: str, store_id: str, zip_code: str):
    if not re.fullmatch(r"\d{5}", zip_code):
        raise CheckoutError("Invalid ZIP")
    try:
        stock = parse_inventory(fetch_inventory(zip_code), zip_code)
    except InventoryError as exc:
        raise CheckoutError(f"Fresh Apple inventory verification failed: {exc}") from exc
    matches = [s for s in stock if s.sku == sku and s.store_id == store_id and s.status == "in_stock"]
    if not matches:
        raise CheckoutError("Requested store/model is no longer confirmed available")
    return matches[0]


def select_button(page, patterns: tuple[str, ...], *, required=True) -> bool:
    """Click exactly one visible enabled UI button, never coordinate-click or guess."""
    for expression in patterns:
        button = page.get_by_role("button", name=re.compile(expression, re.I))
        count = button.count()
        if count == 1 and button.is_visible() and button.is_enabled():
            button.click(timeout=5000)
            return True
    if required:
        raise CheckoutError("Checkout page differs from expected UI; manual action required")
    return False


def select_store(page, store_name: str, zip_code: str) -> None:
    """Try known pickup controls; if store can't be chosen, fail closed."""
    select_button(page, (r"^(?:pick\s*up|pickup|pick up in store)$", r"pick up at an apple store"))
    field = page.get_by_role("textbox", name=re.compile(r"zip|location|postal", re.I))
    if field.count() == 1:
        field.fill(zip_code)
        field.press("Enter")
    else:
        raise CheckoutError("Pickup ZIP entry not uniquely identified")
    page.wait_for_timeout(800)
    candidates = page.get_by_text(store_name, exact=True)
    if candidates.count() != 1:
        raise CheckoutError("Target pickup store not uniquely found")
    candidates.click(timeout=5000)
    # Selection must also be reflected on final review, checked later.


def summary_ok(summary: str, sku: str, store: str, limit: float) -> float:
    """Fail closed unless the final ORDER SUMMARY contains model, color, qty, pickup, and total."""
    if sku not in ALLOWED_SKUS:
        raise CheckoutError("SKU rejected")
    if canonical_store(store) is None:
        raise CheckoutError("Pickup store is not in the five-store allowlist")
    assert_pickup_slot(summary)
    color = "Star White" if sku == "MK1E4LL/A" else "Night Sky"
    normalized = re.sub(r"\s+", " ", summary).lower()
    must = ("iphone duo", "256gb", color.lower(), store.lower(), "pick up")
    if not all(needle in normalized for needle in must):
        raise CheckoutError("Order review does not explicitly verify model, color, storage, and chosen pickup store")
    if any(capacity in normalized for capacity in ("512gb", "1tb", "2tb")):
        raise CheckoutError("Unexpected other storage configuration in order summary")
    if not re.search(r"(?:quantity|qty)\s*:?\s*1\b", normalized):
        raise CheckoutError("Order summary does not prove there is exactly one device")
    if re.search(r"(?:quantity|qty)\s*:?\s*[2-9]", normalized):
        raise CheckoutError("More than one device detected")
    # Price must be labeled 'total' in the local order-summary section.
    matches = re.findall(r"(?:order\s+total|estimated\s+total|total\s+due|total)\s*:?\s*\$\s*([\d,]+(?:\.\d{2})?)", normalized)
    if len(matches) != 1:
        raise CheckoutError("Exactly one labeled order total must be visible")
    amount = float(matches[0].replace(",", ""))
    if not (0 < amount <= limit):
        raise CheckoutError(f"Order total ${amount:.2f} exceeds authorized maximum ${limit:.2f} or is invalid")
    return amount


def find_summary(page) -> str:
    """Only use a dedicated summary container; never scan whole page for validation."""
    selectors = (
        "[data-autom='order-summary']", "[data-testid='order-summary']",
        "#order-summary", ".rs-order-summary", "[aria-label='Order Summary']",
    )
    for selector in selectors:
        el = page.locator(selector)
        if el.count() == 1 and el.is_visible():
            return el.inner_text(timeout=5000)
    raise CheckoutError("Cannot identify verified order summary; refusing to submit payment")


def attempt_page(page, sku: str, store_name: str, zip_code: str, limit: float, allowed_hours: set[int]) -> float:
    """Best-effort Apple flow: never guesses at buttons or bypasses verification."""
    url = BUY_URLS[sku]
    ensure_apple(url)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    ensure_apple(page.url)
    # Site steps change; Apple may require trade-in/carrier/pickup setup first.
    # Only proceed when each button is unique and has the expected accessible label.
    select_button(page, (r"^add to bag$", r"^add to cart$"))
    page.goto("https://www.apple.com/shop/bag", wait_until="domcontentloaded", timeout=30000)
    ensure_apple(page.url)
    select_button(page, (r"^check out$", r"^checkout$"))
    ensure_apple(page.url)
    select_store(page, store_name, zip_code)
    # Continue only if the Apple flow explicitly exposes standard review controls.
    for _ in range(3):
        if any(page.locator(s).count() == 1 for s in ("#order-summary", "[data-autom='order-summary']", "[data-testid='order-summary']", ".rs-order-summary", "[aria-label='Order Summary']")):
            break
        if not select_button(page, (r"^continue$", r"^review order$", r"^review your order$"), required=False):
            break
    ensure_apple(page.url)
    summary = find_summary(page)
    actual = summary_ok(summary, sku, store_name, limit)
    if assert_pickup_slot(summary, require_future=True) not in allowed_hours:
        raise CheckoutError("Requested pickup slot is not one of the authorized future 3:00 or 4:00 PM times")
    final = page.get_by_role("button", name=re.compile(r"^(?:Place (?:Your )?Order|Complete Purchase)$", re.I))
    if final.count() != 1 or not final.is_visible() or not final.is_enabled():
        raise CheckoutError("Verified order is not on the final payment submission screen")
    final.click(timeout=5000)
    return actual


def notify_checkout(title: str, message: str, sku: str) -> None:
    try:
        send_alert(message, title, BUY_URLS.get(sku, "https://www.apple.com/shop/bag"), get_config())
    except Exception as exc:
        LOG.warning("Checkout outcome notification was not delivered: %s", type(exc).__name__)


def attempt(args: argparse.Namespace) -> None:
    auth = read_auth()
    validate_auth(auth, args.sku)
    if PURCHASE_LOCK.exists():
        raise CheckoutError("Prior checkout attempt or purchase lock detected; no repeat orders")
    if not args.store_id or not args.store_name:
        raise CheckoutError("Store identity required")
    # Lock protects against two overlapping alerts; consumed even on error to prevent retries/duplicates.
    secure_directory(LOCK.parent)
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise CheckoutError("Another checkout is running; refusing a duplicate attempt") from exc
    # Durable global lock is written BEFORE navigating checkout, not after payment.
    # A crash or unknown response therefore cannot cause an automatic second order.
    atomic_json(PURCHASE_LOCK, {"status": "checkout_started", "sku": args.sku,
                                "store_id": args.store_id,
                                "started_at": datetime.now(timezone.utc).isoformat()})
    auth["status"] = "attempted"
    auth["attempted_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(AUTH, auth)
    s = verify_stock(args.sku, args.store_id, args.zip_code)
    if s.store.casefold() != args.store_name.casefold():
        raise CheckoutError("Apple changed pickup store identity")
    valid_hours = eligible_pickup_hours(s.store)
    sync_playwright, _ = get_playwright()
    with sync_playwright() as p:
        context = browser_context(p)
        page = context.pages[0] if context.pages else context.new_page()
        try:
            actual = attempt_page(page, args.sku, s.store, args.zip_code, float(auth["max_total_usd"]), set(valid_hours))
            # A click alone does NOT mean the order was accepted. Keep purchase lock either way.
            status = "submitted_unverified"
            try:
                page.wait_for_timeout(2500)
                confirmation = page.locator("body").inner_text(timeout=5000).lower()
                if re.search(r"thank you for your order|order placed|order confirmed", confirmation) and re.search(r"order (?:number|#)", confirmation):
                    status = "confirmed"
            except Exception:
                pass
            atomic_json(PURCHASE_LOCK, {
                "status": status, "sku": args.sku, "store_id": args.store_id,
                "total_usd": actual, "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            print(f"Apple order button clicked: {status}; total validated: ${actual:.2f}.")
            print("Monitoring stops. Check Apple Orders and your email. NEVER rearm without verifying.")
            notify_checkout("Duo checkout halted - verify order", f"Status: {status} for {PRODUCTS[args.sku]} at {s.store}, ${actual:.2f}. No further purchasing is permitted until manual review.", args.sku)
        except Exception as exc:
            print("Automated Apple checkout stopped without a confirmed submission.", file=sys.stderr)
            notify_checkout("Duo checkout needs attention", f"Apple checkout stopped: {type(exc).__name__}. Inspect the Apple checkout and your email; do not rearm before checking for an order.", args.sku)
            if sys.stdin.isatty():
                input("Press Enter to close the Apple browser after inspection: ")
            else:
                page.wait_for_timeout(60_000)
            raise
        finally:
            context.close()
    os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Apple Account login / one-time automated checkout experiment")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("login", help="Sign in securely at Apple in a dedicated local browser")
    a = commands.add_parser("arm", help="Explicitly authorize ONE automated purchase for limited time")
    a.add_argument("--max-total", type=float, required=True, help="Maximum USD charge including tax")
    a.add_argument("--hours", type=float, default=4)
    commands.add_parser("disarm", help="Revoke purchase authorization")
    commands.add_parser("reset-purchase-lock", help="Manually unlock only after checking Apple orders")
    t = commands.add_parser("attempt", help="Triggered by the local stock monitor only")
    t.add_argument("--sku", choices=list(PRODUCTS), required=True)
    t.add_argument("--store-id", required=True)
    t.add_argument("--store-name", required=True)
    t.add_argument("--zip-code", default="01609")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env(Path(".env"))
    try:
        if args.command == "login":
            login()
        elif args.command == "arm":
            arm(args)
        elif args.command == "disarm":
            AUTH.unlink(missing_ok=True)
            print("Authorization revoked; any checkout currently running must also be stopped manually")
        elif args.command == "reset-purchase-lock":
            print("FIRST inspect Apple Orders and your confirmation email for any purchase or pending charge.")
            print("If ANY order was submitted or you are uncertain, do not reset.")
            if input("Type I VERIFIED NO APPLE ORDER to permit a future attempt: ").strip() != "I VERIFIED NO APPLE ORDER":
                raise CheckoutError("Purchase lock retained")
            PURCHASE_LOCK.unlink(missing_ok=True)
            AUTH.unlink(missing_ok=True)
            print("Local purchase lock reset; still disarmed. Re-authorization required.")
        else:
            attempt(args)
    except (CheckoutError, PickupConstraintError, OSError, ValueError) as exc:
        LOG.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
