# Radar phone notifications

Production ordinary Web Push, configured from **BOT → 推送设置**. The existing
`/radar/push-test/` PWA URL, manifest identity, worker storage, subscription, VAPID key,
pair token and increasing sequence are intentionally retained so the accepted
iPhone installation continues working without reinstalling.

## Defaults and behavior

- Real BOT messages, enabled, at most four entries per notification, oldest first.
- A 60-second minimum interval between alerts; messages arriving during it are
  batched. No new eligible message means no periodic notification.
- All R levels received by default, including R5+ and R1000+. Settings allow
  exclusion of ranks, coins, SF/FS/FF types, either exchange, and a minimum
  percentage. Blocking R5 includes R5+; blocking R5+ alone excludes only R5+.
- Only the percentage immediately following the R level in the title is used.
  Net yield/funding percentages in the body are not substituted. Message
  direction and spot/future leg types are checked before accepting an entry.
- Body order: original UTC+8 HH:mm, percentage, R level, type, route, symbol.
  Exchange names: BN, BG, BY, GT, AS, OK, HY. No false live age counters.
- No custom title. iOS still controls app identity, font, wrapping and expansion.
  Four entries do not guarantee four physical lines for long symbols/ranks.
- The worker displays a new notification before closing its captured predecessors.
  Unique tags avoid the WebKit same-tag issue observed during the phone trial.
  Late pushes cannot replace newer content with older content.

The relay reads the authorized publisher feed every three seconds, read-only.
It requires a connected source with a heartbeat no more than 90 seconds old.
Only unseen messages no more than 120 seconds old initiate an alert. Up to
30 minutes of eligible context may appear in the four-row window. A newly
enabled relay can include messages from the preceding 120 seconds. IDs survive
restarts; identical content from different groups within 120 seconds is deduped.
Saving settings preserves eligible pending alerts. Disabling or filtering them
removes those alerts; muted/filtered messages are not replayed.

Send intent is persisted before the network request. Unknown outcomes are not
blindly retried. Explicit 429/5xx responses use bounded backoff and stale pending
signals expire. HTTP 404/410 invalidates the subscription and settings prompts
for reconnection. The production API rejects the old synthetic start/resend
campaign endpoints. Its authenticated `verify` route sends one explicitly marked
four-row diagnostic, at most once per five minutes, after phone subscription
identity has been checked.

## Settings and ownership

The BOT modal saves all settings to the server with a revision check. Pairing
uses the existing owner code behind the site's existing access login, rate
limited to ten attempts in five minutes. Production paired tokens no longer
expire with the original 48-hour trial. Status never exposes subscription URLs,
private keys, bearer tokens or the pairing code. The installed phone's local
storage and worker IDB remain compatible. Do not commit runtime credentials.

API is under `/radar/push-test/api/`: `pair`, `subscribe`, `status`, `settings`,
`receipt`, `receipt-batch`, `device`, `verify`, `health`. Only health/pair are public to the site login; remaining
routes require the paired bearer token. Cross-origin POSTs are rejected.

## Deployment

Python 3.12 and pinned `requirements.txt`, listening on loopback 18885. Existing
paths are retained to preserve credentials and subscription state:

- Code and venv: `/opt/radar-webpush-test/`; static files in `public/`.
- Config: `/etc/radar-webpush-test/config.json`: `pairCode`, legacy `expiresAt`,
  `publicKey`, `privateKeyPath`. VAPID PEM is root/service-group-readable only.
- State: `/var/lib/radar-webpush-test/state.json`, service-owned mode 0600.
  `live.settings` holds preferences, `live.revision` the saved revision.
- Unit: `radar-webpush-test.service`. `RADAR_LIVE_FEED` selects production mode;
  without it, the old finite test backend remains available for isolated tests.
- Feed: `/var/lib/robot-push/feed.json`, mode 0640, group www-data. The service
  has that supplementary group and a read-only filesystem except its state dir.
  Do not bind-mount the individual feed file: the publisher atomically replaces it.
- BOT assets: `notification-settings.js/css`, loaded by its HTML entry point.

For the existing host, `python web/push-test/deploy_live.py` uses the operator's
local SSH config and verified known-hosts file (override with `--ssh-config` and
`--known-hosts`). Paramiko must be installed locally. It stages and tests files,
backs up modified service files, clones the **currently deployed** website under
the existing deployment lock, and adds only the settings module. This preserves
other current web overlays. The publisher is not restarted. On failure, code,
unit and the web symlink are rolled back; the notification sequence is never reset.

This promotion script requires the already installed venv, nginx route and
paired subscription. For a new host, provision those first and authorize the
phone from its home-screen PWA. Keep the existing site access policy.

To pause, disable the toggle in the BOT settings or stop the unit. To roll back,
restore the reported backup files/unit and previous web symlink under the guard
lock, daemon-reload and restart the unit. Retain the current state and sequence.
Never run an old synthetic-only deployment helper against the production relay.

## Verification

```
python -m unittest discover -s web/push-test -p '*_test.py'
node --test web/push-test/sw.test.mjs web/push-test/protocol.test.mjs
node --check web/robot-push/notification-settings.js
```

31 Python tests cover parsing, filtering, batching, persistence, subscription
recovery, bounded verification, Apple credential reuse and secret redaction.
12 worker tests cover replacement, failure preservation, bounded storage access,
offline receipt replay, activation failure and Apple's declarative event shape.

Production acceptance on 2026-10-17: settings opened/saved/reopened in BOT; source
online and the existing phone subscription preserved. The first real APR SF
BG→OK R0 +0.37% message was accepted by Apple (seq 15). The phone's v2 worker
reported rows=1, before=1, closeCalls=1, after=1. This is device processing evidence,
not a claim to have remotely viewed the phone's lock screen. Earlier owner tests
confirmed one remaining notification and the four-entry time-first layout.

## Mobile entry

The installed PWA keeps its existing id, start URL and worker scope at
`/radar/push-test/`. nginx internally serves the current BOT page at that URL
(no external redirect or reinstall). The shared HTML base points to
`/radar/robot-push/`, so assets and feed requests remain canonical. Settings
open only from the BOT toolbar button. Worker updates preserve the subscription,
IndexedDB, notification kind and sequence.
Use `deploy_mobile_entry.py` after the live relay is installed.

## Delivery recovery (2026-10-17)

The phone reported permission `default` and no local subscription while the
server still held a subscription and Apple returned HTTP 201. The settings UI
now compares a SHA-256 fingerprint of the phone's endpoint/key tuple to the
server's fingerprint. It offers a user-initiated repair when absent or mismatched;
it never requests permission automatically. A known mismatch pauses sends to
the stale endpoint. The original reason iOS removed the subscription is not
proven by retained logs.

The worker requests display before persisting the latest sequence. IndexedDB,
notification enumeration and telemetry are bounded so they cannot indefinitely
block display. Receipts are queued locally for later foreground upload. A
`display-requested` receipt proves successful browser API processing and records
remaining notification count; it does not prove that a human saw the lock screen.

Apple VAPID authorization is reused for at least one hour, including across
service restarts, in a mode-0600 state file. Push TTL is five minutes and a stable
Topic coalesces messages queued while offline. Worker v5 supports mutable
Declarative Web Push: WebKit supplies `event.notification` and null `event.data`.
Only a phone reporting v5 receives that envelope; older workers receive ordinary
payloads. The fallback requires the title “雷达”; the normal worker keeps the
previous empty-title layout. System fallback rendering and grouping remain under
iOS control.

Recovery acceptance: after the owner granted permission, the phone reported
`granted`, a present subscription and a matching server fingerprint. Diagnostic
sequence 82 returned both `push-received` and `display-requested` from phone
worker v4, with four entries and `after=1`. This verifies the ordinary payload
path on the phone. The v5 declarative path has protocol tests but has not yet
been confirmed by a phone receipt. Production remains enabled with the existing
four-entry, 60-second settings; no source filters were changed.

References: [Apple Web Push transport](https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers),
[WebKit Declarative Web Push](https://webkit.org/blog/16535/meet-declarative-web-push/),
[WebKit PushEvent implementation](https://github.com/WebKit/WebKit/blob/main/Source/WebCore/Modules/push-api/PushEvent.cpp).
