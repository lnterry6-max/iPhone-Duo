# Duo Stock Scout

**iPhone Duo 256GB pickup restock watcher near Worcester ZIP 01609.** This repository is designed for read-only inventory checks and user-controlled checkout. Watches exactly two Apple U.S. configurations: **Star White (MK1E4LL/A)** and **Night Sky (MK1F4LL/A)**. Never alerts on 512GB/1TB/2TB. Star White is preferred when both appear simultaneously. A match means Apple's current pickup service said `available` at a nearby Apple Store, not that the phone is reserved.

## What it can and cannot do

- ✅ Continuously query Apple's public *pickup status* endpoint every ~20 seconds from an awake, always-on Mac/computer.
- ✅ Alert your phone immediately via **ntfy** and/or **Telegram**, with the correct Apple 256GB product page link and store name. Optionally open the product page on the Mac.
- ✅ Deduplicate alerts until a store/color drops out of stock and reappears; handle network failures as **unknown** rather than incorrectly saying out of stock.
- ✅ Optional GitHub Actions five-minute backup check and automated unit tests.
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

**Important:** GitHub Actions is a five-minute backup, not a 20-second always-on service. To approach a 30-second detection goal, a computer must actually run `watch` continuously while awake and online. Automatic checkout is an experimental, locally armed option, not enabled by default. It cannot guarantee an order; Apple's live flow has not been validated.

## Optional GitHub Actions five-minute backup

`.github/workflows/backup-scan.yml` checks from GitHub runners on a `*/5 * * * *` schedule and can be run manually from **Actions → Optional 5-minute cloud backup scan → Run workflow**.

To receive backup pushes, add a repository Actions secret named `NTFY_TOPIC` (Settings → Secrets and variables → Actions). Optional Telegram secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. It attempts best-effort continuity using Actions cache; if cache is unavailable it may alert twice. Cloud IPs can receive HTTP 541, and cron runs may be delayed or skipped. **Do not use this scheduled workflow for a 30-second guarantee.**

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
