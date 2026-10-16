# iPhone notification experiment

Independent, synthetic-only PWA at `/radar/push-test/`. It does not subscribe to
the BOT feed, use PushWard, or read trading data. The system service cannot read
the robot publisher directories.

## Behavior

An owner enters a temporary eight-digit pairing code, adds the page to the
iPhone home screen, and explicitly grants notification permission there.
After starting, the first push is scheduled 30 seconds later. Seven synthetic
updates follow at 30-second intervals. Each payload is **one notification**
whose body contains the latest one to six sample entries, oldest first.
The seventh update removes the oldest entry. A campaign ends automatically;
there is no periodic feed polling or automatic retry. At most three campaigns
can be started before administrative reset. Pairing/auth expires in 48 hours.

The worker displays the new notification, then enumerates and closes previous
notifications belonging to this test. Unique tags avoid relying on WebKit's
same-tag replacement bookkeeping. If displaying fails, it preserves the old
notification. This is an experiment: installed iOS versions may differ, and
the OS controls collapsed/expanded text layout, wrapping and truncation.
Six newline-separated entries do not guarantee six visible physical lines.

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

11 automated checks passed before initial deployment. Browser page checked;
real-device subscription, delivery, truncation and single-notification behavior
still require device acceptance. No real data integration is authorized here.
