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
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from duo_monitor import BUY_URLS, PRODUCTS, fetch_inventory, parse_inventory, InventoryError, get_config, send_alert, load_env
from pickup_rules import assert_pickup_slot, canonical_store, eligible_pickup_hours, PickupConstraintError

LOG = logging.getLogger("duo_checkout")
PROFILE_ROOT = Path.home() / ".duo-stock-scout"
LOGIN_CONFIRMATION = PROFILE_ROOT / "login-confirmed.json"
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


def checkout_browser() -> str:
    """Playwright channel to use in a separate, local browser profile."""
    choice = os.getenv("CHECKOUT_BROWSER", "chrome").strip().lower()
    if choice not in ("chrome", "chromium"):
        raise CheckoutError("CHECKOUT_BROWSER must be chrome or chromium")
    return choice


def browser_profile() -> Path:
    """Never use an existing personal Chrome profile or Safari cookies."""
    return PROFILE_ROOT / ("apple-browser-chrome" if checkout_browser() == "chrome" else "apple-browser-chromium")


def require_verified_login() -> None:
    """Manual UI confirmation; NOT an assertion that Apple will accept checkout."""
    try:
        confirmed = json.loads(LOGIN_CONFIRMATION.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CheckoutError("No locally verified Apple session. Run checkout_bot.py login and confirm the account page loads.") from exc
    if confirmed.get("browser") != checkout_browser():
        raise CheckoutError("The verified login belongs to a different browser. Run checkout_bot.py login again.")
    if time.time() - float(confirmed.get("verified_at", 0)) > 86400:
        raise CheckoutError("Local login check is older than 24 hours; verify Apple sign-in again.")
    

def chrome_cli() -> Path:
    """Official Playwright CLI already installed by the user locally."""
    return Path.home() / ".local" / "bin" / "playwright-cli"


def connected_chrome_ready() -> bool:
    """Check the existing attached Chrome; never connect remotely or export cookies."""
    if sys.platform != "darwin" or os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        return False
    binary = chrome_cli()
    if not binary.is_file():
        return False
    try:
        result = subprocess.run([str(binary), "-s=chrome", "tab-list"],
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=12, check=False)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def arm(args: argparse.Namespace) -> None:
    mode = get_config()["checkout_mode"]
    if mode == "chrome_auto":
        if not connected_chrome_ready():
            raise CheckoutError("Chrome isn't connected. Open normal Chrome and run playwright-cli attach --extension=chrome.")
    elif mode == "experimental":
        require_verified_login()
    else:
        raise CheckoutError("Your monitor is in manual checkout mode. Automatic purchases are not armed.")
    if PURCHASE_LOCK.exists():
        raise CheckoutError("A checkout was already attempted. Check Apple orders first; the purchase lock must be explicitly reset.")
    if not (1999 <= args.max_total <= 3000):
        raise CheckoutError("Set a dollar maximum between $1999 and $3000 (including tax)")
    if not (0 < args.hours <= 24):
        raise CheckoutError("Authorization expires within 24 hours")
    print("This authorizes ONE real Apple order for a 256GB iPhone Duo.")
    print(f"Browser checkout mode: {mode}.")
    print("Allowed colors: Star White or Night Sky; allowed quantity: one.")
    print(f"Maximum total price including tax: ${args.max_total:.2f}.")
    print("If Apple changes the page or requests verification, checkout will stop.")
    if input("To authorize an automatic charge, type BUY ONE DUO: ").strip() != "BUY ONE DUO":
        raise CheckoutError("Not armed; confirmation phrase did not match")
    atomic_json(AUTH, {
        "status": "armed", "expires_at": time.time() + 3600 * args.hours,
        "max_total_usd": args.max_total, "quantity": 1,
        "allow_submit": True, "checkout_mode": mode,
        "armed_at": datetime.now(timezone.utc).isoformat(),
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
    profile = browser_profile()
    secure_directory(profile)
    choice = checkout_browser()
    options = {
        "user_data_dir": str(profile),
        "headless": False,
        "accept_downloads": False,
        "viewport": {"width": 1150, "height": 850},
    }
    # Use the installed regular Google Chrome rather than the bundled Chrome for Testing.
    # This is normal supported Playwright functionality, not an attempt to evade site security.
    if choice == "chrome":
        options["channel"] = "chrome"
    try:
        return playwright.chromium.launch_persistent_context(**options)
    except Exception as exc:
        raise CheckoutError(
            "Cannot open the selected browser. For CHECKOUT_BROWSER=chrome, install regular "
            "Google Chrome; otherwise select chromium locally. Browser error: " + type(exc).__name__
        ) from exc


def login() -> None:
    # A spinning Apple sign-in screen must never be treated as a saved login.
    LOGIN_CONFIRMATION.unlink(missing_ok=True)
    print(f"Opening a dedicated local {checkout_browser()} profile (not your personal Safari/Chrome cookies).")
    print("Sign in ONLY on Apple's official site in the opened window; complete any verification yourself.")
    print("If Apple shows an endless spinner or sends you back to sign-in, do NOT confirm.")
    sync_playwright, _ = get_playwright()
    response = ""
    with sync_playwright() as p:
        context = browser_context(p)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto("https://www.apple.com/shop/account/home", wait_until="domcontentloaded", timeout=30000)
            print("Check the Apple Store Account page, not just the sign-in prompt.")
            response = input(
                "ONLY if your account details are visible on Apple's Store Account page, "
                "type VERIFIED; otherwise press Enter to cancel: "
            ).strip()
        finally:
            context.close()
    if response != "VERIFIED":
        raise CheckoutError("Login not verified; unattended checkout stays disarmed.")
    atomic_json(LOGIN_CONFIRMATION, {"browser": checkout_browser(), "verified_at": time.time()})
    print("You confirmed the account page loaded. Session remains LOCAL and may still expire.")


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


def parse_care_inspection(output: str) -> dict:
    """Accept only a narrow allowlist of nonsensitive AppleCare UI labels."""
    raw = output.strip()
    if not raw or len(raw) > 50000:
        raise CheckoutError("Care inspection returned invalid output")
    try:
        quoted = json.loads(raw)
        if isinstance(quoted, str):
            raw = quoted
    except ValueError:
        pass
    marker = "DUO_CARE_INSPECT="
    pos = raw.rfind(marker)
    if pos < 0:
        raise CheckoutError("No sanitized AppleCare inspection result received")
    try:
        result, _ = json.JSONDecoder().raw_decode(raw[pos + len(marker):].lstrip())
    except ValueError as exc:
        raise CheckoutError("AppleCare inspection result was malformed") from exc
    if not isinstance(result, dict) or result.get("status") not in (
        "controls_found", "no_visible_care_controls", "not_on_apple", "inspection_failed"
    ):
        raise CheckoutError("Unexpected AppleCare inspection status")
    controls = result.get("controls", [])
    if not isinstance(controls, list) or len(controls) > 20:
        raise CheckoutError("Unexpected AppleCare control list")
    filtered = []
    for control in controls:
        if not isinstance(control, dict):
            raise CheckoutError("Unexpected AppleCare control entry")
        role, label = control.get("role"), control.get("label")
        if not isinstance(role, str) or not isinstance(label, str):
            raise CheckoutError("Unexpected AppleCare control format")
        if len(role) > 30 or len(label) > 140:
            raise CheckoutError("Unexpectedly long AppleCare label")
        if not re.search(r"applecare|no coverage|without coverage|no thanks|decline (?:coverage|applecare)|protection plan", label, re.I):
            continue
        filtered.append({"role": role, "label": label, "disabled": bool(control.get("disabled"))})
    return {"status": result["status"], "controls": filtered}


def inspect_applecare() -> None:
    """Inspect ONLY care-related control labels on the currently selected Apple tab."""
    if not connected_chrome_ready():
        raise CheckoutError("Chrome extension is disconnected. Reattach to normal Chrome.")
    script = Path(__file__).with_name("inspect_applecare.js")
    if not script.is_file():
        raise CheckoutError("The safe AppleCare inspector script is missing")
    try:
        proc = subprocess.run(
            [str(chrome_cli()), "-s=chrome", "--raw", "run-code", f"--filename={script}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=20, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CheckoutError("Read-only AppleCare inspection timed out") from exc
    if proc.returncode:
        raise CheckoutError("Unable to inspect the active Chrome tab")
    result = parse_care_inspection(proc.stdout)
    if result["status"] == "not_on_apple":
        raise CheckoutError("Select an apple.com product tab before inspecting")
    if result["status"] == "inspection_failed":
        raise CheckoutError("AppleCare controls could not be inspected")
    if not result["controls"]:
        print("No visible AppleCare controls detected on this tab.")
        print("Apple may show coverage only at a later configurator or bag step.")
        return
    print("Visible AppleCare-related controls (read-only; no selections made):")
    for item in result["controls"]:
        print(f"  {item['role']}: {item['label']}")


def parse_chrome_cli_result(output: str) -> dict:
    """Read only our prefixed, structured CLI result; never print raw page data.

    Depending on CLI version, --raw may still JSON-quote a returned JS string.
    Decode that outer string first, then strictly parse one result dictionary.
    """
    value = output.strip()
    if not value or len(value) > 200000:
        raise CheckoutError("Chrome checkout returned an empty or oversized result")
    try:
        decoded = json.loads(value)
        if isinstance(decoded, str):
            value = decoded
    except (ValueError, TypeError):
        pass
    marker = "DUO_AUTOMATION_RESULT="
    position = value.rfind(marker)
    if position < 0:
        raise CheckoutError("Chrome checkout returned no verified machine-readable outcome")
    fragment = value[position + len(marker):].lstrip()
    try:
        answer, _ = json.JSONDecoder().raw_decode(fragment)
    except ValueError as exc:
        raise CheckoutError("Chrome checkout result could not be verified") from exc
    if not isinstance(answer, dict) or answer.get("status") not in (
        "stopped", "review_verified", "submitted_unverified"
    ):
        raise CheckoutError("Chrome checkout result was unexpected")
    return {
        key: answer[key]
        for key in ("status", "stage", "code", "clickedOrderButton", "total_usd")
        if key in answer
    }


def chrome_checkout_flow(stock, max_total: float, allowed_hours: list[int],
                         *, submit_order: bool) -> dict:
    """Execute a strict local CLI script in existing Chrome; NEVER print browser data."""
    if not connected_chrome_ready():
        raise CheckoutError("Connected Chrome session is unavailable; automation aborted.")
    canonical = canonical_store(stock.store)
    if canonical is None or stock.sku not in ALLOWED_SKUS:
        raise CheckoutError("SKU or store outside the authorized five-store/256GB allowlist")
    if not allowed_hours or any(h not in (15, 16) for h in allowed_hours):
        raise CheckoutError("No allowed future October 27 pickup hours remain")
    url = BUY_URLS[stock.sku]
    config = {
        "sku": stock.sku, "store": canonical, "zip": stock.zip_code,
        "url": url, "quantity": 1, "max_total_usd": float(max_total),
        "valid_hours": list(sorted(set(allowed_hours))), "submit_order": bool(submit_order),
    }
    template = Path(__file__).with_name("chrome_checkout_flow.js").read_text(encoding="utf-8")
    if template.count("__DUO_CONFIG_JSON__") != 1:
        raise CheckoutError("Chrome purchase template was modified unexpectedly")
    secure_directory(PROFILE_ROOT)
    script = PROFILE_ROOT / f"chrome-flow-{os.getpid()}.js"
    data = template.replace("__DUO_CONFIG_JSON__", json.dumps(config, ensure_ascii=True))
    binary = str(chrome_cli())
    try:
        with script.open("x", encoding="utf-8") as file:
            os.chmod(script, 0o600)
            file.write(data)
        # The CLI already has the user's signed-in Chrome extension connection.
        # tab-new only navigates the selected 256GB product; never logs in.
        navigate = subprocess.run(
            [binary, "-s=chrome", "tab-new", url],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=25, check=False,
        )
        if navigate.returncode != 0:
            raise CheckoutError("Could not open approved product in connected Chrome")
        result = subprocess.run(
            [binary, "-s=chrome", "--raw", "run-code", f"--filename={script}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=100, check=False,
        )
        # CLI may print page-related details on error; NEVER log raw CLI output.
        if result.returncode != 0:
            raise CheckoutError("Chrome checkout scripting could not finish safely")
        return parse_chrome_cli_result(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise CheckoutError("Chrome checkout timed out; order outcome is uncertain") from exc
    finally:
        script.unlink(missing_ok=True)


def attempt_chrome(args: argparse.Namespace) -> None:
    """Explicitly armed one-shot order attempt using the existing Chrome extension."""
    if get_config()["checkout_mode"] != "chrome_auto":
        raise CheckoutError("Set CHECKOUT_MODE=chrome_auto locally for this explicit opt-in")
    auth = read_auth()
    validate_auth(auth, args.sku)
    if auth.get("checkout_mode") != "chrome_auto":
        raise CheckoutError("Checkout authorization was created for another browser mode")
    if PURCHASE_LOCK.exists():
        raise CheckoutError("A prior order attempt is already locked; NEVER retry blindly")
    if not args.store_id or not args.store_name:
        raise CheckoutError("Specific Apple Store identity required")
    # All nonpayment prerequisites are checked BEFORE creating the durable lock.
    stock = verify_stock(args.sku, args.store_id, args.zip_code)
    if stock.store.casefold() != args.store_name.casefold():
        raise CheckoutError("Apple Store identity changed")
    hours = sorted(eligible_pickup_hours(stock.store))
    if not connected_chrome_ready():
        raise CheckoutError("Your signed-in Chrome session disconnected")
    secure_directory(LOCK.parent)
    fd = os.open(LOCK, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Acquire exclusive lock, re-read auth and purchase state to avoid races.
        validate_auth(read_auth(), args.sku)
        if PURCHASE_LOCK.exists():
            raise CheckoutError("Purchase already locked by another attempt")
        atomic_json(PURCHASE_LOCK, {
            "status": "checkout_started", "sku": args.sku,
            "store_id": args.store_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
        })
        auth["status"] = "attempted"
        auth["attempted_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(AUTH, auth)
        try:
            result = chrome_checkout_flow(stock, float(auth["max_total_usd"]), hours, submit_order=True)
            if result["status"] == "submitted_unverified":
                status = "submitted_unverified"
                msg = "One order button click attempted; check your Apple Orders and email immediately."
            else:
                status = "stopped_before_confirmation"
                msg = "Checkout stopped; verify Apple Orders before considering any reset."
            atomic_json(PURCHASE_LOCK, {
                "status": status, "sku": args.sku, "store_id": args.store_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            LOG.warning("%s; purchase lock remains set.", msg)
            notify_checkout("Duo checkout halted - verify", msg, args.sku)
        except Exception as exc:
            LOG.error("Automated Chrome checkout stopped (%s). Purchase lock remains.", type(exc).__name__)
            notify_checkout("Duo checkout needs attention",
                "Chrome checkout stopped or timed out. Verify Apple's order page and email before any reset.",
                args.sku)
            raise
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def dry_run_chrome(args: argparse.Namespace) -> None:
    """Safe functional test: may add to bag, never clicks Apple's final order button."""
    if not connected_chrome_ready():
        raise CheckoutError("Chrome extension is not attached")
    if args.sku not in ALLOWED_SKUS:
        raise CheckoutError("Not an allowed iPhone Duo SKU")
    from duo_monitor import Stock
    from pickup_rules import canonical_store
    canonical = canonical_store(args.store_name)
    if canonical is None:
        raise CheckoutError("Store is not on the approved list")
    hours = sorted(eligible_pickup_hours(canonical))
    stock = Stock(canonical, "LOCAL-TEST", args.sku, PRODUCTS[args.sku], "unknown", args.zip_code)
    result = chrome_checkout_flow(stock, args.max_total, hours, submit_order=False)
    LOG.info("Review-only Chrome test result: %s (no purchase submitted)", result.get("status"))
    if result.get("status") == "stopped":
        LOG.warning("Stopped at %s: %s. Inspect Chrome manually; do not enable auto until the flow is understood.",
                    result.get("stage"), result.get("code"))
    elif result.get("status") == "review_verified":
        LOG.info("Apple review summary matched restrictions; final order NOT clicked.")
    else:
        raise CheckoutError("Unexpected dry-run state")


def attempt(args: argparse.Namespace) -> None:
    require_verified_login()
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
    commands.add_parser("inspect-applecare", help="Read-only Chrome AppleCare labels; no cart or payment changes")
    commands.add_parser("reset-purchase-lock", help="Manually unlock only after checking Apple orders")
    t = commands.add_parser("attempt", help="Triggered by the local stock monitor only")
    ca = commands.add_parser("attempt-chrome", help="One-shot live Chrome extension checkout; requires arm")
    d = commands.add_parser("dry-run-chrome", help="Test Chrome checkout to final review without payment")
    d.add_argument("--sku", choices=list(PRODUCTS), required=True)
    d.add_argument("--store-name", required=True)
    d.add_argument("--zip-code", default="01609")
    d.add_argument("--max-total", type=float, default=2200)
    t.add_argument("--sku", choices=list(PRODUCTS), required=True)
    t.add_argument("--store-id", required=True)
    t.add_argument("--store-name", required=True)
    t.add_argument("--zip-code", default="01609")
    ca.add_argument("--sku", choices=list(PRODUCTS), required=True)
    ca.add_argument("--store-id", required=True)
    ca.add_argument("--store-name", required=True)
    ca.add_argument("--zip-code", default="01609")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_env(Path(".env"))
    try:
        if args.command == "login":
            login()
        elif args.command == "arm":
            arm(args)
        elif args.command == "inspect-applecare":
            inspect_applecare()
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
        elif args.command == "attempt-chrome":
            attempt_chrome(args)
        elif args.command == "dry-run-chrome":
            dry_run_chrome(args)
        else:
            attempt(args)
    except (CheckoutError, PickupConstraintError, OSError, ValueError) as exc:
        LOG.error("%s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
