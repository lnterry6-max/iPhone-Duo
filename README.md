# iPhone Duo Stock Scout — five-store pickup watcher

A local, opt-in Apple Store pickup monitor for **one iPhone Duo 256GB** in **Star White** or **Night Sky**. It uses Apple's unofficial read-only pickup status response; it is **not affiliated with Apple**.

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

**Never enter your Apple password, 2FA code, card number, or authenticated session cookies into GitHub, this chat, or GitHub Actions secrets.** You can sign in to Apple directly inside the isolated browser on your own Mac.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-checkout.txt
python -m playwright install chromium
python checkout_bot.py login
```

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
