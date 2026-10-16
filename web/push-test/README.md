# iPhone notification experiment

Independent, synthetic-only PWA at `/radar/push-test/`. It does not subscribe to
the BOT feed, use PushWard, or read trading data. The system service cannot read
the robot publisher directories.

## Behavior

An owner enters a temporary eight-digit pairing code, adds the page to the
iPhone home screen, and explicitly grants notification permission there.
After starting, the first push is scheduled 30 seconds later. Seven synthetic
updates follow at 30-second intervals. Each payload is **one notification**
whose body contains the latest one to four sample entries, oldest first.
From the fifth update onward, each update removes the oldest entry. A campaign ends automatically;
there is no periodic feed polling or automatic retry. At most three campaigns
can be started before administrative reset. Pairing/auth expires in 48 hours.

The worker displays the new notification, then enumerates and closes previous
notifications belonging to this test. Unique tags avoid relying on WebKit's
same-tag replacement bookkeeping. If displaying fails, it preserves the old
notification. This is an experiment: installed iOS versions may differ, and
the OS controls collapsed/expanded text layout, wrapping and truncation.
Four newline-separated entries do not guarantee four visible physical lines.
The accepted layout is time, percentage, rank, type, route, symbol. The title
is empty; iOS still supplies application identity. BY means Bybit and HY means
Hyperliquid. Proportional system fonts do not guarantee table-like alignment.

## Diagnostics and acceptance

- HTTP 201 records only Apple's acceptance, not delivery.
- Worker receipts record display requests and notification enumeration counts.
- A device screenshot/owner observation determines whether the lock screen
  really contains one notification and whether all entries can be read.
- A receipt is saved locally before network upload; opening the paired page
  resubmits it when a Cloudflare Access session has expired in the background.
- No endpoint, private subscription key or bearer token is returned by status.

## Server

Python 3.12, `requirements.txt`; loopback port 18885. Install the static files
under `/opt/radar-webpush-test/public`, server/venv under its parent, and the
included systemd unit as `radar-webpush-test.service`.

Config `/etc/radar-webpush-test/config.json` holds `pairCode`, `expiresAt`,
`publicKey` (base64url uncompressed P-256 point), and `privateKeyPath`.
Keep it and the private VAPID PEM root-owned, group-readable only to the service.
State `/var/lib/radar-webpush-test/state.json` is mode 0600, service-owned.
Do not commit any of these runtime credentials or subscriptions.

The nginx snippet adds a separate static/API route under the existing protected
site. Keep existing Cloudflare Access authentication in place. Stopping the
systemd service stops all future test sends; a running campaign is marked
interrupted after a restart and never resumes automatically.

## Checks

```
python -m unittest discover -s web/push-test -p server_test.py
node --test web/push-test/sw.test.mjs
node --check web/push-test/app.js
```

Device tests confirmed a single remaining notification and four readable entries.
The owner accepted the time-first layout on 2026-10-17. These results apply to
the tested iPhone; they are not a cross-device guarantee. Real data integration
is not enabled or authorized by this test. Temporary pairing still expires
after 48 hours; this is not an always-on production service.
