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

## Chrome verification read fix (October 26, 9:46 PM)

The supervised checkout dry run still reached `applecare / care_challenge_check` but stopped with `challenge_page_unreadable`. The iPhone Duo configurator was visibly open in Chrome. This strongly suggests a Playwright full-page-reading problem, **not proof that Apple blocked the session**.

To avoid transferring the full Apple product configurator's enormous text over Playwright's extension connection, the verification check now uses **read-only `page.evaluate()` inside Chrome** and returns only `readable`, `unreadable`, or `human_verification`. This does not disable challenge detection. Captcha/human-verification content still stops the bot immediately; unreadable pages retry up to 3 **read-only** times and then stop. No credentials, cookies, complete snapshots, or page text are exported by the checker.

The project retains an explicitly supervised **nonpaying** dry run. To test it after checking your bag for unintended old test items, keep normal Chrome connected to Playwright and run:

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py dry-run-chrome --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

Keep `AUTO_CHECKOUT=false`. If it stops, share only its final `Stopped at ... / ... : ...` diagnostic. It may add a phone to the bag but never presses the final order button. This does **not** prove Apple supports fully automatic checkout.

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

## October 26, 9:53 PM — no-AppleCare label selection update

After the Chrome verifier became readable, the live dry run stopped at `applecare / care_wait_for_render / no_applecare_option_missing`, even though a prior read-only inspection showed **No AppleCare coverage** as an input and label. Two issues were addressed:

- The Chrome checkout launcher already opens the approved 256GB URL. The script now **skips a redundant second navigation** when already on that exact approved URL, avoiding a needless React configurator reset.
- The AppleCare selection now reads visible DOM `label` text *inside Chrome*, matches only **No AppleCare coverage**, identifies its linked `radio` or `checkbox`, clicks the label via Playwright, and checks that the linked input really becomes selected. Unlinked, ambiguous, unreadable, or absent options stop safely. It never guesses a paid AppleCare plan. The selection wait is bounded and may last around 25 seconds during page loading.

To retry safely after checking your Apple bag for earlier test items:

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py dry-run-chrome --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

This command is **review-only and never presses Apple's final order submission button**. Keep `CHECKOUT_MODE=chrome_extension` and `AUTO_CHECKOUT=false`. Passing offline tests does not demonstrate that Apple will accept an automated transaction, bypass verification, or meet a 30-second purchase target.

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

## October 26, 10:37 PM — pickup option works; no in-store offer yet

The latest supervised `dry-run-bag` successfully clicked Apple's **“I'll pick it up”** choice, then stopped safely at `pickup / pickup_after_choice / zip_entry_missing`. The user reports that no approved stores currently show pickup inventory. This is **not proof** that every store is sold out at the same moment; the screenshots establish only that this checkout session did not provide the ZIP control our script expected. Earlier Apple's private pickup endpoint also returned HTTP 541, so automated restock detection cannot currently be relied upon.

The checkout script now waits briefly for a ZIP/location field rather than assuming it exists instantly. If Apple's page **explicitly states** that there are no stores offering pickup, it reports `pickup_no_stores_available`. If it explicitly says the selected store is unavailable, it reports `pickup_requested_store_unavailable`. Otherwise, it continues to report `zip_entry_missing` to avoid falsely treating unknown layouts or a single unavailable location as every store being sold out. **Never force delivery** or pick another store/time not on the user allowlist.

No order has been submitted. Keep the exact one-phone shopping bag, **no paid AppleCare**, and `AUTO_CHECKOUT=false`. Don't repeatedly rerun the dry run while no acceptable pickup inventory is being offered; wait for Apple to show an eligible store and the approved October 27, 3:00/4:00 PM slot, then continue safely. A phone sitting in the bag is **not** a reservation.

## October 26, 10:34 PM — “I'll pick it up” at checkout

The bag-only dry run reached **Apple's pickup versus delivery selection** but stopped at `pickup / bag_checkout_verify / expected_control_missing`. The checkout flow previously expected a generic `Pick Up` button, while Apple actually shows **“I'll pick it up”**.

The script now waits for the **exact pickup choice** (including the curly-apostrophe variant), selects its regular button, link, or radio control, and rejects **delivery** and **Apple Pay/Express Checkout** options. If the choice is absent or a human-verification challenge appears, it stops instead of guessing. This is still an unvalidated live integration.

**Because your shopping bag already contains one 256GB Star White Duo, use the bag-only command; do not add another phone:**

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py dry-run-bag --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

The test should click **Check Out → I'll pick it up**, then attempt to find Apple's store search/location field. It can stop there if the interface differs. No order is submitted, `AUTO_CHECKOUT=false` must remain in your local `.env`, and your current bag does not reserve pickup inventory.

## Resume the existing Apple bag without adding another phone

**October 26 evening:** The real Chrome dry run reached `https://www.apple.com/shop/bag`, showing **one iPhone Duo 256GB Star White** and a displayed bag total of **$2,123.94**. The checkout code then stopped with `bag_checkout_ambiguous` because Apple's bag may have more than one identical **Check Out** control. The standard Checkout selector now chooses the first enabled exact-match button (or matching link) and **never** matches `Check out with Apple Pay`.

**Important:** Because a phone is already in the bag, do NOT rerun `dry-run-chrome` until you have removed previous test products; that command starts from the product page and can add another unit. Instead use this newly supported nonpaying **bag-only resume**:

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py dry-run-bag --sku MK1E4LL/A --store-name Natick --zip-code 01609 --max-total 2200
```

This opens the **existing bag** in attached Chrome, confirms the Star White 256GB item text is present, selects only a standard Checkout control, and attempts to navigate store/pickup choices. It **does not** click Place Order, cannot charge, and **does not add another phone**. It refuses `resume_bag` if payment submission is enabled. Before running, visually ensure the bag contains **exactly one phone** with no unwanted extras. A later order-review check must independently verify device, quantity, store, appointment, no AppleCare, and the authorized price ceiling.

The screenshot showed **pickup unavailable at Blackstone Valley** at the time, but that does not confirm status for Natick or other allowed stores. Avoid assuming that a bag item reserves store inventory or that the requested next-day appointment will be offered. Continue to keep `AUTO_CHECKOUT=false` until checkout has been safely verified in the real Apple Store.

## Faster stock-to-Chrome handoff (October 26, 2026)

The monitor formerly checked **all five ZIP codes** before handling even the first valid, new, eligible stock response, and then sent notification requests before opening Chrome. That could add substantial avoidable latency. It now:

- Begins the handoff immediately when a configured ZIP first returns **new in-stock inventory for one approved 256GB Duo at an allowed store**. Other ZIP codes are not fetched in that round after the eligible hit, and previous statuses from unqueried stores are preserved.
- Starts the Chrome handoff **before** waiting on ntfy or Telegram, which can each take up to 12 seconds.
- In `CHECKOUT_MODE=chrome_extension` and `STOCK_ACTION=notify`, asks **regular Google Chrome directly** to open the approved product page using native macOS `open -a` without waiting for a Playwright CLI round trip. Falls back to the connected CLI if that launch fails. The user's existing browser session is reused without copying credentials.

This is a *latency optimization*, **not faster inventory polling**: five ZIP locations still need coverage over healthy rounds, the watcher's rate-limit interval is still at least 120 seconds, a live pickup time is not guaranteed, and Apple HTTP 541 means the stock feed is unavailable (not sold out). The tool cannot promise to catch a fleeting restock. It will not bypass Apple's human verification or automatically place an order in the recommended setup.

Recommended settings for a fast nonpaying browser handoff (local `.env`):

```dotenv
CHECKOUT_MODE=chrome_extension
STOCK_ACTION=notify
BROWSER_APP=Google Chrome
OPEN_BROWSER=true
AUTO_CHECKOUT=false
POLL_SECONDS=120
```

An optional `NTFY_TOPIC` can deliver urgent push notifications to the ntfy phone app. Use `python3 duo_monitor.py test-alert` to verify a configured notification channel. With no configured channel, this will open a Chrome tab on stock if available, but will not deliver a phone alert.

## Payment-readiness preflight (October 26, 2026)

The repo now has a **no-payment, no-inventory-request** readiness check:

```bash
cd ~/iPhone-Duo
git pull
python3 checkout_bot.py preflight
```

It reports the exact Duo configuration, approved stores, October 27 3/4 PM deadline, one-order lock, Chrome connection, local authorization and selected action mode. It explicitly reports the two unverified prerequisites: **fresh Apple stock** and **verified final checkout summary showing the exact pickup store/date/time/price**. **A passing GitHub test suite or simulated restock cannot replace these checks.** The command never enables checkout or accesses payment information.

**To run the safest usable monitor tonight** (opens Chrome when real eligible stock is detected, then you complete purchase yourself), keep your local `.env` set to:

```dotenv
CHECKOUT_MODE=chrome_extension
STOCK_ACTION=notify
BROWSER_APP=Google Chrome
OPEN_BROWSER=true
AUTO_CHECKOUT=false
POLL_SECONDS=180
```

Then use `python3 duo_monitor.py watch`. The alert feed is still subject to Apple's HTTP 541 refusal. The watcher backs off and exits after three consecutive failed checks, rather than silently claiming to monitor stock or bypassing security checks. **If 541 continues, you must rely on Apple's own product availability display or another independent legitimate restock alert; no reliable automatic purchase is possible from a failed feed.**

**Do not switch `CHECKOUT_MODE=chrome_auto` and `AUTO_CHECKOUT=true` solely based on simulated tests.** The checkout bot's final payment and the October 27 appointment have not been successfully validated. The existing delivery order may create an unwanted second purchase, and the persistent one-order lock must not be reset without verifying Apple Orders. Never put Apple credentials, verification codes, payment information, browser tokens or cookies in GitHub.

## Stock-triggered checkout testing (safe and nonpaying)

The Apple API stock monitor can now **automatically launch one checkout dry run when a qualifying 256GB Duo is detected as in stock**. This uses the same approved five-store list and October 27 3:00/4:00 PM time-window constraints as the original monitor. It **never presses Place Order** in this mode. **Apple's inventory endpoint has returned HTTP 541 in practice**, so this is *not* a guaranteed or currently verified live restock detector; it will stop after repeated failures rather than evading Apple's verification.

### Configure your local Mac

Leave Chrome open with its authorized Playwright extension connection, and make sure your Apple bag has **one and only one approved iPhone Duo** (do not add a cheaper test product to the existing Duo bag). In **local `.env` only**, set:

```dotenv
CHECKOUT_MODE=chrome_extension
STOCK_ACTION=dry_run_bag
AUTO_CHECKOUT=false
OPEN_BROWSER=false
POLL_SECONDS=180
```

With this configuration, any *new* qualifying in-stock response causes the monitor to send a notification and start the existing-bag **`checkout_bot.py dry-run-bag`**, which may navigate checkout but **can never submit an order**. A durable one-time `.state/stock-dry-run-claimed.json` prevents duplicate dry-run launches. The claim does **not** mean a purchase was accepted. The only order-acceptance signal is Apple's confirmation.

### Test the trigger without Apple's inventory endpoint

```bash
cd ~/iPhone-Duo
git pull
python3 duo_monitor.py simulate-stock --sku MK1E4LL/A --store-name Natick
```

This injects a **fake in-stock event** solely to test the allowlist and one-shot launcher; it is **NOT evidence that Natick actually has the phone**. It will launch the **nonpaying** existing-bag browser dry run if configured as above. The checkout log is at `.state/stock-dry-run.log`. Simulation uses a **separate** `.state/simulated-stock-dry-run-claimed.json` so testing cannot suppress a future real restock. Repeating the simulation will not launch another browser checkout unless the user deliberately resets its test claim. Invalid SKUs or stores are refused.

### Test visible Apple pickup UI with another product (no purchase)

To test that Playwright can read a **known in-stock accessory or different Apple product**, open its public product page manually in the same normal Chrome, select that tab, and manually open Apple's public pickup-availability panel if offered. Run:

```bash
python3 checkout_bot.py inspect-test-product
```

This is a **read-only inspector**. It reports up to 15 short visible pickup-related control labels and names of the five approved stores visible on the page. It does **not** click, add to bag, navigate, claim a restock, or submit payment. Observing a different product in stock does **not** qualify the phone for purchase; real matching remains hard-limited to SKUs `MK1E4LL/A` and `MK1F4LL/A`.

### Read-only inspector update — October 26, 10:58 PM

The configured Apple Watch Series 12 page exposed **The Shops at Blackstone Valley** but no actionable pickup-related control labels. This establishes that the Playwright inspector can read a named Apple Store, **not that the Watch or iPhone Duo is in stock**.

The inspector now also checks **very short local text immediately adjacent to the exact approved store name**, without exporting full page content. It reports `available`, `unavailable`, or `unknown`, **only for that test product** and only when the local UI explicitly provides a signal. If text is absent or conflicting it prints `unknown`. It never makes a purchase, navigates, modifies your bag, or triggers a Duo checkout.

To retest in existing Chrome:

```bash
cd ~/iPhone-Duo
git pull
"$HOME/.local/bin/playwright-cli" -s=chrome tab-select 2
python3 checkout_bot.py inspect-test-product
```

If the Watch page displays no pickup indication for the selected configuration, an `unknown` result is expected. Real Duo stock detection remains a separate unresolved problem: the private Apple pickup requests were returning HTTP 541. Do not treat another product's status as authorization to purchase a Duo.

### Turn on read-only inventory monitoring

```bash
python3 duo_monitor.py watch
```

If Apple refuses the pickup requests with 541, **do not use proxy rotation or verification bypasses**. The monitor marks stock **unknown**, backs off, and stops after three failed rounds. A working normal Chrome tab does not prove the private inventory endpoint is responding. Stock alerts are not confirmations that the exact October 27 pickup window is available.

**Critical:** Automatic payment using `CHECKOUT_MODE=chrome_auto` remains experimental and is **not approved by these tests**. Do not enable it based on this setup. Any future purchasing mode must verify the exact SKU, quantity, no paid AppleCare, approved store, October 27 appointment and total cap immediately before submission, and must permanently block duplicates or unknown outcomes.

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
