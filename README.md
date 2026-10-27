# iPhone Duo Stock Scout — five-store pickup watcher

A local, opt-in Apple Store pickup monitor for **one iPhone Duo 256GB** in **Star White** or **Night Sky**. It uses Apple's unofficial read-only pickup status response; it is **not affiliated with Apple**.

## Use your everyday Safari or Chrome (recommended)

If the separate Playwright sign-in window keeps spinning after Apple verification, **stop trying to sign in there**. You can use the Safari or Chrome browser where your Apple Account is already signed in. The monitor opens Apple's matching product page in a new normal browser tab when it sees stock at one of the five approved stores.

In your *local, uncommitted* `.env`, set:

```dotenv
CHECKOUT_MODE=browser_handoff
BROWSER_APP=Safari
OPEN_BROWSER=true
AUTO_CHECKOUT=false
```

To use your ordinary Google Chrome instead, set `BROWSER_APP=Google Chrome`. `BROWSER_APP=Default` opens your macOS default browser. If you already cloned the repo, run `git pull` first; `git pull` does **not** replace your local `.env`. A changed `.env.example` also does not automatically update `.env`.

Test a handoff without buying anything:

```bash
python3 duo_monitor.py prepare-checkout
```

This opens the Star White 256GB product page in your selected existing browser; you can sign in and verify the product page yourself. It does **not** add to a bag, select pickup, or place an order. To watch new stock:

```bash
python3 duo_monitor.py watch
```

**Browser handoff is intentionally manual checkout.** The Python checkout bot's Playwright persistent-context launcher cannot safely reuse Chrome's regular main profile, and it cannot control installed Safari. However, Microsoft's separate Playwright Extension/CLI can connect to Chrome tabs you already have open; see the supported diagnostic approach below. It is now wired into the **stock monitor's safe tab-opening flow**, but **not** into the experimental Python payment/checkout bot. A manual tab handoff uses your existing session without copying passwords, cookies, verification codes, or card details. The stock check alone does not confirm the exact October 27 pickup appointment; you must check 3:00/4:00 PM in Apple's checkout.

`CHECKOUT_MODE=browser_handoff` ensures the monitor **never starts the automated purchase process**, even if an old local `AUTO_CHECKOUT=true` value remains. Experimental checkout is a separate, explicitly configured mode; it is not recommended when Apple refuses to complete sign-in in a dedicated browser.

## Optional: officially supported Playwright Extension for regular Chrome

If Chrome for Testing hangs during Apple sign-in, stop using that separate browser. Microsoft's [Playwright Extension](https://chromewebstore.google.com/detail/playwright-extension/mmlmfjhmonkocbjadbfplnigmagldckm) supports connecting to **existing** regular Chrome tabs and their already-authenticated sessions. This is a normal integration, **not a means of bypassing bot verification, Apple two-factor checks, CAPTCHA, or checkout protections**.

For a safe read-only diagnostic on your own Mac:

1. Open your normal Google Chrome and manually sign in at https://www.apple.com/shop/account/home. Confirm the account page actually loads.
2. Install **Playwright Extension**, published by Microsoft, from the official Chrome Web Store. Give only the permissions you intend; browser-control extensions can access sensitive authenticated pages. Do not share its access/connection token.
3. Install the official CLI using a current Node.js installation, then attach:

```bash
npm install -g @playwright/cli@latest
playwright-cli attach --extension=chrome
playwright-cli snapshot
```

The snapshot is for diagnostics only: verify that the CLI can inspect your normal Chrome tab. Do not copy account details, cookies, or tokens into logs or GitHub. If the extension asks to select/authorize the browser session, approve it locally. If Chrome or Apple shows a verification challenge, complete it yourself normally or stop; do not attempt to automate around it.

**Important: the repository's existing Python `checkout_bot.py` does not use the extension**. It still launches a separate Playwright browser profile, so switching to this extension does not automatically enable unattended payment. Attaching Chrome is a potential foundation for a *future* checkout assistant that navigates to an order review and asks you to confirm the final purchase. For now, use `CHECKOUT_MODE=browser_handoff`, `BROWSER_APP=Google Chrome`, `AUTO_CHECKOUT=false`, and test without placing an order.

Microsoft documentation: [Connecting to Browsers](https://playwright.dev/mcp/configuration/browser-extension) and [Playwright CLI](https://playwright.dev/docs/getting-started-cli).

## Connected Chrome extension handoff (now integrated)

Your normal Chrome + Microsoft Playwright Extension connection can now be used by **the stock monitor**. This is a tested-at-the-code-level, **manual payment** handoff, not fully automatic checkout. When a matching SKU first comes in stock at one of the five approved stores, the monitor runs the installed Playwright CLI command `-s=chrome tab-new <approved-Apple-product-URL>` against the **existing Chrome session** and opens a tab to the correct 256GB phone. It **never runs `open`** (which creates a new browser profile), and never reads browser cookies, account snapshots, passwords, or payment information.

### On your Mac

Update your local checkout monitor and local `.env`:

```bash
cd ~/iPhone-Duo
git pull
open -e .env
```

Set these values in the **uncommitted** `.env`:

```dotenv
CHECKOUT_MODE=chrome_extension
BROWSER_APP=Google Chrome
OPEN_BROWSER=true
AUTO_CHECKOUT=false
```

Before starting, leave your regular Chrome and Playwright Extension running and connect it using:

```bash
"$HOME/.local/bin/playwright-cli" attach --extension=chrome
```

If it says the `chrome` session is already attached, leave it attached; do not run `playwright-cli open`.

### Test without making a purchase

```bash
python3 duo_monitor.py prepare-checkout
```

This should open the **Star White 256GB** product page in a new tab of your *already attached* Chrome, without touching your shopping bag or attempting checkout. Then use `python3 duo_monitor.py watch` to monitor restocks.

If your Chrome extension session has disconnected (for example, you closed the tab it was attached to), the monitor will **fall back to opening the product in ordinary Chrome** with a warning rather than launching Chrome for Testing. You may need to reconnect the extension.

**These are still two independent systems:** `duo_monitor.py` can open a product tab via the official Chrome extension; the experimental `checkout_bot.py` is unchanged and would still launch its *separate browser profile* if explicitly selected. In `CHECKOUT_MODE=chrome_extension`, `AUTO_CHECKOUT` has no purchasing effect. No Apple order is submitted, and you must verify your requested October 27 3:00/4:00 PM pickup and place an order manually. The monitor cannot detect a manually completed purchase. **As soon as Apple confirms your order**, run this command in another Terminal window while the monitor is running:

```bash
cd ~/iPhone-Duo
python3 duo_monitor.py mark-purchased
```

Type `ORDER CONFIRMED` when prompted. This creates a durable purchase lock in `~/.duo-stock-scout/purchase-lock.json`; the watcher sees it within about a second, exits, and will refuse further checks after restart. Run this **only after an accepted order**, not merely after a button click. If an Apple order was not accepted, do not mark it purchased. `mark-purchased` does not submit, cancel, or modify an Apple order.

Chrome extension access is powerful and may include sensitive open tabs. Do not upload the extension connection token, session snapshots, or browser logs to GitHub, and do not bypass any Apple login or human verification checks.

## No AppleCare+ preference and safer dry-run reporting

The Chrome checkout script now explicitly looks for Apple's **No AppleCare+ coverage** or **No AppleCare coverage** selection on the product page, and never chooses a paid AppleCare+ or AppleCare One plan. If the no-coverage option cannot be uniquely found, it **stops** instead of guessing. A final order review that explicitly shows a paid AppleCare plan is also rejected.

The CLI result parser now handles the JSON-quoted response format that previously produced `Chrome checkout result could not be verified`. When a dry run stops, the CLI only logs sanitized values such as `stage=applecare` and `code=no_applecare_option_missing`; never share full browser snapshots, orders, credentials, or payment details.

**Before retrying:** manually check your Apple Shopping Bag and remove any item the previous dry run may have added. Do not re-run a checkout test with an existing phone in the bag. After `git pull`, make sure `AUTO_CHECKOUT=false`, then start a non-paying dry run:

```bash
cd ~/iPhone-Duo
python3 checkout_bot.py dry-run-chrome --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

A dry run may navigate checkout and change the shopping bag, but **will never click the final order submission button**. It can still encounter Apple authentication requirements; the script stops rather than bypassing verification. These checks are offline-tested; Apple's actual UI and available pickup appointment are not yet validated.

## Recovering from HTTP 541 and testing readiness

If your Mac logs `Apple refused the request (HTTP 541)`, **stop the watcher with Control+C**. This means inventory is unknown, *not* out of stock. Do not use proxy rotation, automated CAPTCHA solvers, account-sharing, or other verification bypasses. Apple's undocumented pickup API is not guaranteed to remain available.

The monitor now limits the watch interval to **at least 120 seconds** when five ZIPs are configured, uses a larger retry delay following errors, and **stops after three consecutive failed inventory rounds** instead of retrying indefinitely. The recommended interval in `.env.example` is **180 seconds**. After `git pull`, edit your existing local `.env` manually:

```dotenv
POLL_SECONDS=180
CHECKOUT_MODE=chrome_extension
BROWSER_APP=Google Chrome
OPEN_BROWSER=true
AUTO_CHECKOUT=false
```

For a **no-network, no-purchase** readiness check of your local browser connection:

```bash
cd ~/iPhone-Duo
python3 duo_monitor.py doctor
```

This checks the named `chrome` extension session without inspecting, saving, or printing private Chrome pages. If disconnected, reconnect using `"$HOME/.local/bin/playwright-cli" attach --extension=chrome`. The doctor does not test Apple inventory or payment acceptance. In particular, **passing unit tests or doctor checks does not make unattended checkout safe to enable**.

### Staged Apple checkout testing

The experimental checkout code on `main` is **not validated in Apple's live store** and may leave a product in the bag while investigating. Never set `CHECKOUT_MODE=chrome_auto` or `AUTO_CHECKOUT=true` simply because browser attachment succeeds. A safe next milestone is a user-supervised, **nonpaying** dry run that can inspect product/configuration, pickup-store choices, and an order review while refusing final order submission. Treat any Apple security/2FA challenge as a stop requiring normal manual verification. Never upload credentials, snapshots, cookies, tokens, payment details, or personal checkout output.

A completed Apple order cannot be inferred from clicking a button; use Apple's own confirmation. The one-order persistent lock is essential even if checkout crashes or an outcome remains uncertain. An already existing delivery order may result in a second phone purchase.

## October 26: observed AppleCare choice and next nonpaying test

The user's read-only Chrome inspector identified an actual `label` and `input` called **No AppleCare coverage**. Paid options labeled **AppleCare+ with Theft and Loss** and **AppleCare One** were also present. The earlier dry run stopped at `no_applecare_option_missing` because its immediate selection check could not see a matching control.

The Chrome checkout script now waits up to **12 seconds** for the exact no-coverage label or radio to render, chooses **only** that option, and verifies that its linked radio/checkbox is **checked**. It refuses to proceed if the choice is absent or does not register. The final order summary must explicitly show **No AppleCare coverage**, without a paid AppleCare line. Nothing in the checkout dry-run submits payment, and none of this has been proven against a live accepted purchase.

After checking your Apple bag for old test items, pulling updates, and ensuring the existing Chrome extension connection is active, you can rerun:

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py dry-run-chrome --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

Keep `AUTO_CHECKOUT=false`. The dry run may still stop on a later unrecognized Apple control; the reported stage/code should guide further nonpaying diagnostics. Avoid sharing any account data or Chrome session tokens.

## AppleCare labeled-input fix (October 26, 9:33 PM)

The supervised dry run advanced to Apple's AppleCare selection but returned `stopped at applecare: checkout_interface_unrecognized`. **No purchase was submitted.** This generic error could be caused by the old wrapper-label check, but the live underlying exception has not been inspected.

The updated Chrome flow prefers Playwright's `page.getByLabel(/^No AppleCare(?:\\+)? coverage$/i)` to locate Apple's radio input, calls `check()` only when necessary, and verifies `isChecked()`. It rejects ambiguous labels and uses a strictly verified label fallback. The controlled result now includes a narrow `step` identifier (for example, `care_select_control`, `care_verify_control`) without logging personal page content.

To test **without authorizing payment**, check your bag for test items, ensure Chrome remains connected, then run:

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py dry-run-chrome --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

Keep `AUTO_CHECKOUT=false`, and do not arm the purchase bot. If it stops again, share only the final `Stopped at ... / ... : ...` line; do not share Apple session tokens, private page snapshots, or payment information. The test may manipulate the phone configuration or bag but will **not** press Place Order.

## Troubleshoot a missing No AppleCare+ option (read-only)

If `dry-run-chrome` stops with `Stopped at applecare: no_applecare_option_missing`, the page did **not** expose the exact selection label the automation expected. That does **not** mean AppleCare is compulsory; the option may be worded differently or presented later.

**Do not enable automatic checkout to diagnose this.** Instead:

1. In your existing, Playwright-connected **normal Chrome**, select the iPhone Duo 256GB product tab (not the Apple Account, bag, or payment tab). Navigate the visible product configurator manually if needed, until you see an AppleCare section.
2. From `~/iPhone-Duo`, run the **read-only** control inspector:

```bash
python3 checkout_bot.py inspect-applecare
```

The inspector never clicks anything, makes an order, reads cookies, or exports a page snapshot. It only prints the **short visible labels** matching AppleCare/coverage-related controls from the selected Apple tab. If nothing appears, it reports that the option is not currently visible, which can mean Apple presents it only after another normal product choice.

Do not share private session information or the full Playwright snapshot. If the controls report different wording, the selector can be adjusted based on those observed labels. A purchase flow must still reject any additional protection plans and check the final order total. Existing Apple checkout automation has **not** been proven safe for unattended payment and must remain disabled until manually tested.

## Exactly five Apple Stores

Only these five stores are accepted by `pickup_rules.py`. Every other store returned by Apple is ignored for stock events, alerts, and checkout.

| Store | City | Address |
| --- | --- | --- |
| The Shops at Blackstone Valley | Millbury | 70 Worcester-Providence Turnpike, Millbury, MA 01527 |
| Natick | Natick | 1245 Worcester Street, Natick, MA 01760 |
| Boylston Street | Boston | 815 Boylston Street, Boston, MA 02116 |
| Chestnut Hill | Chestnut Hill | 199 Boylston Street, Chestnut Hill, MA 02467 |
| Legacy Place | Dedham | 508 Legacy Place, Dedham, MA 02026 |

**No Google Maps API key, route service, or paid mapping service is required.** Restricting inventory to these stores **does not verify that you can drive to them in an hour**. Especially for Boston-area stores, traffic could make your original one-hour goal impossible. Check travel times yourself before authorizing a purchase.

The app watches exactly these two SKUs:
- Star White 256GB — `MK1E4LL/A`
- Night Sky 256GB — `MK1F4LL/A`

It does not monitor or purchase 512GB, 1TB, or 2TB variants.

## Required pickup date and time

The only acceptable appointment is **Tuesday, October 27, 2026 at exactly 3:00 PM or 4:00 PM (Eastern)**. This constraint is hard-coded in `pickup_rules.py`; monitoring and checkout will stop qualifying candidates after those times pass. Apple inventory being available **does not mean** it has your requested appointment.

For checkout, `checkout_bot.py` will only attempt final payment after the **Apple order summary** explicitly shows that date and either exact time, the correct Apple Store, the correct 256GB color, quantity one, and a total within the amount you authorized. If Apple does not offer the pickup slot, or if the automation cannot find its controls, it **stops without intentionally placing an order**. This flow is experimental and has **not been verified on a completed Apple purchase**.

## Install on your Mac

Requires Python 3.11 or newer, an internet connection, and a Mac that remains awake.

```bash
git clone https://github.com/lnterry6-max/iPhone-Duo.git
cd iPhone-Duo
cp .env.example .env
open -e .env
```

Or, if you've already cloned the project, update it first with `git pull`, then update your local `.env` to use:

```dotenv
ZIP_CODES=01609,01760,02116,02467,02026
POLL_SECONDS=20
PREFERRED_COLOR=Star White
AUTO_CHECKOUT=false
CHECKOUT_MODE=browser_handoff
BROWSER_APP=Safari
OPEN_BROWSER=true
```

These ZIP codes are only entry points into Apple's **nearby-store** inventory response. Apple can return extra stores, but our code filters them out. Multiple queries take time and might cause Apple to limit requests. The 20-second interval is **the pause between checks**, not a guaranteed start-to-start frequency or checkout speed. Never use proxy rotation to evade rate limits.

### iPhone notifications

1. Install the [ntfy app](https://ntfy.sh/) and subscribe to a new long, random, private topic name.
2. Set `NTFY_TOPIC=that-unique-topic` in local `.env`. Never publish the topic.
3. Test and perform a read-only lookup:

```bash
python3 duo_monitor.py test-alert
python3 duo_monitor.py once --no-notify
```

4. Start the stock watcher:

```bash
python3 duo_monitor.py watch
```

Alerts include the detected store, color, and Apple product page. Optional Telegram alerts use local `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`; do not share those values. The watcher only runs while the computer is awake and connected. You can install the macOS login agent using `bash scripts/install_macos.sh`, but a closed/sleeping MacBook will not poll.

## Optional experimental local automated checkout

This separate mode is **not compatible with attaching to your everyday Chrome profile or installed Safari session**. It requires an independent browser session that must already have successfully completed Apple's sign-in flow. If you cannot authenticate within that browser, do not use it. Enabling the experimental mode requires `CHECKOUT_MODE=experimental` AND `AUTO_CHECKOUT=true`; default `browser_handoff` does not purchase.



**Never enter your Apple password, 2FA code, card number, or authenticated session cookies into GitHub, this chat, or GitHub Actions secrets.** You can sign in to Apple directly inside the isolated browser on your own Mac.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-checkout.txt
python -m playwright install chromium
python checkout_bot.py login
```

The bot now opens **regular installed Google Chrome**, using a dedicated local profile (`~/.duo-stock-scout/apple-browser-chrome`) rather than Chrome for Testing. This is separate from your normal Safari and Chrome logins. In `.env`, keep `CHECKOUT_BROWSER=chrome`. Install normal Chrome first if it is not already installed. Playwright supports this browser channel, but Apple may still refuse or fail to finish sign-in.

**Important sign-in check:** if Apple's sign-in page keeps spinning, redirects back to sign-in, or never shows your account details, return to Terminal and press Enter to cancel. The bot will *not* treat that as an authenticated session. Type `VERIFIED` only after you can visibly access your Apple Store Account page in **the same automated Chrome window**. That acknowledgment expires after 24 hours and is not proof that Apple will allow checkout later.

For diagnosis, first sign in manually using **ordinary Chrome outside the bot** (without importing/exporting cookies). If regular Chrome works but this dedicated automated Chrome window does not, leave `AUTO_CHECKOUT=false`: use the stock monitor's alerts and Apple's normal Safari checkout manually. Do not copy browser session cookies, bypass verification challenges, or store your password in GitHub.

Check that your Apple bag is empty, your payment details are correct, and Apple has the right account. **If you already have a delivery order, an additional pickup order would be a second purchase.** Decide how to handle the existing order first.

Explicitly authorize one charge with an inclusive maximum and expiration:

```bash
python checkout_bot.py arm --max-total 2200 --hours 4
```

Type the confirmation phrase in your own Terminal when asked. This is a **real-purchase authorization**, not a dry run. Set `AUTO_CHECKOUT=true` in your local `.env` only after testing stock checks and understanding the limitations, then run:

```bash
python duo_monitor.py watch
```

The bot uses a persistent Playwright browser profile at `~/.duo-stock-scout/apple-browser`. This directory contains sensitive session cookies; it must remain on your private local computer. Apple can still require interactive verification, payment confirmation, or other human action, and the automation will not bypass these.

### Permanent stop after one checkout attempt

At the **beginning of the first checkout attempt**, the bot writes a durable `~/.duo-stock-scout/purchase-lock.json`. The local monitor detects that lock, **shuts down**, and refuses any future checkout attempt—even if the process crashes or Apple never confirms the order. Restarting `watch` or arming again does not bypass it. This prevents accidental repeat purchases while order status is uncertain. A submitted button click is **not proof of order acceptance**: inspect Apple's Orders page and confirmation email.

Only if you've independently verified that **no Apple order exists or is pending**, you may explicitly clear this lock and reauthorize:

```bash
python checkout_bot.py reset-purchase-lock
```

This operation requires a typed confirmation; it does **not** re-arm purchasing. To revoke an unspent authorization, use `python checkout_bot.py disarm`.

## GitHub Actions

The **Tests** workflow runs offline unit tests on commits. The **Manual cloud stock scan** is read-only and runs only when you manually select **Actions → Manual cloud stock scan → Run workflow**. No recurring GitHub scanner or cloud checkout is enabled, so a local purchase lock cannot be bypassed by scheduled background purchases. Never store Apple sign-in credentials in GitHub.

## Run tests

```bash
python3 -m unittest discover -s tests -v
```

Tests use simulated Apple inventory and checkout summaries; they do not make real purchases or prove the live Apple checkout is compatible.

## Limitations

- Apple can change, throttle, or block its undocumented pickup endpoint (e.g. HTTP 403/429/541). A failed query means **unknown**, not sold out.
- An "in stock" response does not reserve inventory or prove a 3/4 PM pickup appointment is available.
- No mapping API is used, therefore **the one-hour driving limit is no longer verified**. The five named stores are the selection boundary.
- Because several ZIP-code queries and checkout steps are needed, **a purchase within 30 seconds cannot be promised**.
- Automatic checkout remains **experimental and unvalidated on a real transaction**. It deliberately fails closed when the Apple site differs from expectations.
- Keep `.env`, purchase state, notification credentials, and browser profiles uncommitted. Your repository is currently public.

Apple Store: https://www.apple.com/shop/buy-iphone/iphone-duo
