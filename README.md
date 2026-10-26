# Duo Stock Scout

**iPhone Duo 256GB pickup restock watcher near Worcester ZIP 01609.** This repository is designed for read-only inventory checks and user-controlled checkout. Watches exactly two Apple U.S. configurations: **Star White (MK1E4LL/A)** and **Night Sky (MK1F4LL/A)**. Never alerts on 512GB/1TB/2TB. Star White is preferred when both appear simultaneously. A match means Apple's current pickup service said `available` at a nearby Apple Store, not that the phone is reserved.

## What it can and cannot do

- ✅ Continuously query Apple's public *pickup status* endpoint every ~20 seconds from an awake, always-on Mac/computer.
- ✅ Alert your phone immediately via **ntfy** and/or **Telegram**, with the correct Apple 256GB product page link and store name. Optionally open the product page on the Mac.
- ✅ Deduplicate alerts until a store/color drops out of stock and reappears; handle network failures as **unknown** rather than incorrectly saying out of stock.
- ✅ Manual-only GitHub Actions cloud stock scan and automated unit tests (no scheduled scanning after purchase).
- 🧪 **Experimental opt-in local checkout attempt** in `checkout_bot.py`. With a previously authenticated Apple browser session and a one-time time-limited local authorization, it *can attempt* to add to bag, select pickup, verify the final order and submit it. **This has not been validated on Apple’s live checkout**; it fails closed when Apple’s interface cannot be verified, and it may need user intervention. No public supported auto-purchase API, no CAPTCHA/MFA bypass. Not affiliated with Apple.
- ⚠️ **The 30-second goal applies only to best-case detection**, not guaranteed alert delivery or completed checkout. Apple can return HTTP 403/429/541, change its undocumented response, delay inventory, or rate-limit repeated queries. Cloud-hosted checks may be blocked. GitHub Actions schedule is not a 20-second timer.

Apple purchase price: **$1,999 before tax**. By default the links choose unlocked / connect later, so you can evaluate using your existing mobile carrier without signing up for a new line. Inspect the final order details yourself before purchasing.

## Setup on a Mac (recommended for fastest checks)

**Requirements:** Python 3.11+ (`python3 --version`), active internet, Mac awake (sleeping laptops cannot poll), and an iPhone to receive notifications.

1. Make a private, long/random notification topic. In the [ntfy app](https://ntfy.sh/) on your iPhone, subscribe to that topic (example: `duo-01609-a43a9c7f1b2b4e4b8de9`, but use your own). Anyone who knows the topic may be able to read public-server notifications. Enable push permissions.
2. To prepare the fastest *user-approved* checkout, open Apple's product page from your own computer and sign in with Apple directly through your normal browser. The command below opens the correct Star White 256GB page; you can also sign in on the Night Sky product page. If you save a payment method with Apple, Apple may reuse it at checkout. Two-factor authentication or other payment authorization may still be required. The stock monitor never receives your Apple password, verification codes or payment details. The optional Playwright browser profile stores **local session cookies**, which are sensitive: keep the profile on your own Mac, never share or commit it.

   ```bash
   python3 duo_monitor.py prepare-checkout
   ```

3. In Terminal, go into the extracted project folder and configure it:

   ```bash
   cp .env.example .env
   open -e .env
   ```

   In `.env` set `NTFY_TOPIC=` to the exact same private/random topic. The default ZIP is `01609`, the default frequency is 20 seconds, and **only the two 256GB colors are monitored**.
4. Test notifications and then test Apple's live endpoint:

   ```bash
   python3 duo_monitor.py test-alert
   python3 duo_monitor.py once --no-notify
   ```

   The first sends a clearly identified **test** push. The second calls Apple for real and prints what it sees without modifying notification state. If Apple returns HTTP 541/403/429, do not treat that as out of stock; cloud IPs are especially susceptible.
5. Start continuous monitoring:

   ```bash
   python3 duo_monitor.py watch
   ```

   Keep Terminal open, Mac awake, and connected. Stop with `Ctrl+C`. For automatic restart/login on macOS, run `bash scripts/install_macos.sh` once and consult `~/Library/Logs/duo-stock-scout.error.log` (the installer creates a local macOS LaunchAgent). You can also use an always-on personal Linux computer, mini PC or VPS, but VPS IPs may be blocked by Apple.

### Connected GitHub repository

The project is published at https://github.com/lnterry6-max/iPhone-Duo . To run on your Mac, clone it with `git clone https://github.com/lnterry6-max/iPhone-Duo.git` and then `cd iPhone-Duo`. Configure `.env` locally and run the commands above. If you decide to make the public repository private, choose **Settings → General → Danger Zone → Change repository visibility**. Do not commit `.env`, notification topics, Apple credentials or session cookies. `.gitignore` excludes `.env` and `.state`.

**Important:** GitHub Actions is manual-only, not a 20-second always-on service. To approach a 30-second detection goal, a computer must actually run `watch` continuously while awake and online. Automatic checkout is an experimental, locally armed option, not enabled by default. It cannot guarantee an order; Apple's live flow has not been validated.

## Optional GitHub Actions manual cloud stock scan

`.github/workflows/backup-scan.yml` can be triggered on demand from **Actions → Optional 5-minute cloud backup scan → Run workflow**.

To receive backup pushes, add a repository Actions secret named `NTFY_TOPIC` (Settings → Secrets and variables → Actions). Optional Telegram secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. It attempts best-effort continuity using Actions cache; if cache is unavailable it may alert twice. Cloud IPs can receive HTTP 541, and cron runs may be delayed or skipped. **There is no scheduled workflow; it will not send restock alerts after the local purchase lock is set unless you manually run it.**

## Monitor preferences

Edit `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `ZIP_CODES` | `01609` | Apple returns its nearest pickup stores. Add a comma-separated nearby ZIP (e.g. `01609,01760`) only if you want extra coverage; this increases request traffic. |
| `POLL_SECONDS` | `20` | Time between rounds, plus ±2 sec jitter. Minimum enforced is 15 sec, with exponential backoff after errors. |
| `PREFERRED_COLOR` | `Star White` | If multiple newly in-stock matches appear together, determine which product URL the primary alert opens. Both colors are still monitored. |
| `NTFY_TOPIC` | empty | ntfy notification topic subscribed to on your phone. |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | empty | Optional additional push channel. |
| `OPEN_BROWSER` | `false` | If `true` on a Mac, opens the Apple product page on first availability. **Does not check out.** |
| `STATE_PATH` | `.state/stock.json` | Local deduplication state. Excluded from Git. |

The monitor checks Apple Store pickup only. It does not check in-store inventory at T-Mobile, Best Buy or carrier checkout, and it does not buy shipping inventory. For exact store radius filters or carrier-specific payment plans, additional retailer integrations would be necessary. The Apple response determines which stores are geographically near the requested ZIP; **the monitor does not enforce an exact mileage radius**.

## Troubleshooting

- **HTTP 541 / 403 / 429:** Apple refused the query. The monitor treats it as unknown, backs off instead of hammering the service, and keeps its previous state. No stock claims can be made until a successful response. Apple's endpoint is unofficial and could stop working entirely.
- **No pushes:** Ensure `NTFY_TOPIC` matches the topic subscribed to in the iPhone app, notifications are allowed, and `python3 duo_monitor.py test-alert` succeeds. A test push does **not** mean real stock.
- **No new alerts during prolonged availability:** This is intentional deduplication. The watcher alerts again when Apple has first reported out-of-stock and then in-stock for that store/color.
- **On a MacBook:** Closing the lid usually suspends polling. A login LaunchAgent does not keep a sleeping device awake. Use a genuinely always-on computer if coverage must be 24/7.
- **Apple product link doesn't keep selection:** Recheck the exact model/color/storage on Apple's page before checkout; store pickup inventory and checkout availability may diverge.

## Automated tests

```bash
python3 -m unittest discover -s tests -v
```

Tests use fake Apple pickup responses and checkout summaries; **no actual purchase is attempted**. A successful unit test does not confirm live inventory, checkout, or notifier delivery.

## Technical sources

- Apple Store configuration and price: https://www.apple.com/shop/buy-iphone/iphone-duo
- Apple's read-only pickup endpoint: `https://www.apple.com/shop/retail/pickup-message?pl=true&location=01609&parts.0=MK1E4LL%2FA&parts.1=MK1F4LL%2FA`
- Example technical analysis of the endpoint and possible HTTP 541 responses: https://github.com/bilune/apple-pickup-monitor

Do not try to circumvent CAPTCHA, account security, rate limits, or payment authorization requirements. If Apple's terms or API availability change, disable polling or adjust it appropriately.

## Experimental sneaker-bot-style checkout (local-only)

This optional component is **off by default**. It does not ask for Apple credentials in Terminal or in the GitHub repository. You sign in on Apple's official site in an isolated local browser profile; Playwright reuses that browser session. The profile contains sensitive cookies and is stored under `~/.duo-stock-scout/apple-browser` with owner-only permissions. Do not copy that directory, publish it, or use it on shared/cloud machines. Apple may expire the session or require 2FA, Apple Pay confirmation, or CAPTCHA; the bot cannot bypass these.

Before trying this, **cancel or account for your existing iPhone Duo order**: you could otherwise authorize a second purchase. Remove all other products from your Apple shopping bag. The bot is limited to **one** 256GB Duo for pickup at a store confirmed by Apple's inventory feed. Its automation selectors are deliberately strict and **untested with a completed Apple checkout**; until tested interactively it may stop for manual intervention rather than complete a purchase.

On your Mac (requires desktop session, Chromium, and Python 3.11+):

```bash
python3 -m pip install -r requirements-checkout.txt
python3 -m playwright install chromium
python3 checkout_bot.py login
```

Only enter your Apple ID/password and any 2FA code **on Apple's own sign-in page**, not in this codebase or this chat. Prepare your Apple payment and pickup preferences manually, and check the bag is empty. Once your session is saved, opt in to exactly one real charge, with an inclusive tax cap and a four-hour window; the confirmation phrase is typed locally on your Mac:

```bash
python3 checkout_bot.py arm --max-total 2200 --hours 4
```

Change `AUTO_CHECKOUT=false` to `AUTO_CHECKOUT=true` in your local `.env`, and start the 20-second watcher:

```bash
python3 duo_monitor.py watch
```

When the monitor sees new stock, it sends the alert and attempts checkout in the locally signed-in browser, **only if armed**. The bot rechecks the exact SKU/store in real time, attempts bag and pickup selection, and requires a uniquely identified order summary confirming color, 256GB, **Qty: 1**, pickup store, and a labeled total below your preset cap before it may click Apple's final order button. Otherwise, **it refuses the charge**. Authorization is consumed on the first attempt, including a failed attempt; it will not keep trying to buy. Its experimental log is `.state/checkout-bot.log`. No guarantee of checkout within 30 seconds. Apple may interrupt automated checkout.

Disarm when you no longer want a purchase:

```bash
python3 checkout_bot.py disarm
```

The `login` browser is **not** your everyday Safari login. A Safari session cannot simply be reused by Playwright. GitHub Actions only makes read-only inventory requests; it must never receive your Apple Account password, 2FA codes, payment details, or browser cookies. The experiment does not try to defeat Apple anti-bot, CAPTCHA or payment security.

## October 27, 2026 pickup-only rules and one-purchase shutdown

These rules are enforced in `pickup_rules.py`, `duo_monitor.py`, and `checkout_bot.py`. All five Apple Stores below are considered, **not** automatically assumed within a one-hour drive:

| Apple Store | Official address |
| --- | --- |
| The Shops at Blackstone Valley | 70 Worcester-Providence Turnpike, Millbury, MA 01527 |
| Natick | 1245 Worcester Street, Natick, MA 01760 |
| Boylston Street | 815 Boylston Street, Boston, MA 02116 |
| Chestnut Hill | 199 Boylston Street, Chestnut Hill, MA 02467 |
| Legacy Place | 508 Legacy Place, Dedham, MA 02026 |

A store is eligible only when **both** conditions hold:
1. Google Maps Routes API returns a traffic-aware drive of **at most 55 minutes** from `ORIGIN_ADDRESS` (default: approximate Worcester ZIP 01609) for a departure one hour before the desired pickup time. The five-minute margin helps protect the user's strict **one-hour maximum**, but cannot guarantee actual travel times or account for the exact home address. Boston-area traffic may make Boylston Street, Chestnut Hill, or Legacy Place ineligible.
2. Apple's **final checkout order summary** explicitly shows pickup on **Tuesday, October 27, 2026**, at **exactly 3:00 PM or 4:00 PM**. The stock endpoint alone never proves a pickup timeslot. If Apple's checkout cannot confirm the date and time, **automatic payment is refused**. When Apple needs manual date/time selection, the bot stops rather than guessing or placing an unwanted order.

### Configure traffic-aware driving eligibility

You must have a locally configured **Google Maps Platform Routes API** key; the API requires billing. Enable the Routes API and create a restricted API key in Google Cloud, with sensible quotas and budget alerts, then set `GOOGLE_MAPS_API_KEY=...` inside the local, uncommitted `.env`. See [official Google setup](https://developers.google.com/maps/documentation/routes/get-api-key) and [billing details](https://developers.google.com/maps/documentation/routes/usage-and-billing).

By default, routing starts from **Worcester, MA 01609**, not your exact location. If a precise drive-time constraint is important, set `ORIGIN_ADDRESS` **locally** to your real departure point, but never commit it or send it to GitHub. Routes data is an estimate, not a guarantee.

For wider Apple Store inventory coverage, set `ZIP_CODES=01609,02116,02467,02026`. These search ZIPs do **not** change the driving origin. Checking multiple ZIPs can take longer and trigger Apple's rate limits; do not use proxy rotation or evade traffic controls.

If the Routes API key, traffic estimate, allowed store, or Apple pickup timeslot is missing or cannot be verified, the bot **does not buy**. Missing route verification also suppresses qualifying stock alerts rather than advertising stores as one-hour-eligible without evidence.

### Hard stop after a first checkout attempt

**Once any automated checkout attempt begins**, a persistent file is written to `~/.duo-stock-scout/purchase-lock.json`. The monitor notices the lock, exits within about a second of its next sleep check, and never places a second order. The purchase lock survives a reboot and **even a crash or an ambiguous order submission**. A possible Apple order is treated as `submitted_unverified` until independently confirmed. A successful confirmation page can mark it `confirmed`; a click alone is not proof of purchase.

The lock cannot be bypassed just by restarting `watch` or running `arm` again. Before considering a new attempt, check **Apple Orders, payment activity, and email** to make sure no purchase exists or is pending. Only if you independently verify *no order was made*, use:

```bash
python3 checkout_bot.py reset-purchase-lock
```

This requires a typed confirmation on your own computer, clears local authorization, and **does not automatically re-arm**. Never reset a lock after an accepted or uncertain purchase. **Do not delete or edit the lock manually.**

### Security and operational limitations

- **Do not add Apple Account passwords, verification codes, payment numbers, or browser session cookies to GitHub, including Actions secrets.** A private repo or encrypted secret does not make a shopping password safe to use in cloud automation. Sign in only directly with Apple in the dedicated local browser.
- GitHub Actions remains a read-only, manual stock-check option with no recurring schedule. It never checks out or receives the sensitive checkout browser session.
- This checkout flow is experimental and has **not** been tested on a live accepted Apple order. Apple may require manual authentication, select a different pickup time, change page selectors, or refuse automated browser actions.
- **Under-30-second checkout is not verified or guaranteed.** Google Routes validation and multiple inventory ZIPs add latency, and the request may be rate-limited.

Run offline tests: `python3 -m unittest discover -s tests -v`.
