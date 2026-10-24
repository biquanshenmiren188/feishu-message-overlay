# Radar phone notifications

Production ordinary Web Push, configured from **BOT → 推送设置**. The existing
`/radar/push-test/` PWA URL, manifest identity, worker storage, subscription, VAPID key,
pair token and increasing sequence are intentionally retained so the accepted
iPhone installation continues working without reinstalling.

## Android Web Push (2026-10-17)

Android Chrome and Firefox can enable notifications directly in a normal browser
tab or installed app. Open BOT → 推送设置 → 通知与推送码 → 开启通知 and allow
notifications. Android code switching moves this browser's subscription and loads
the destination settings; desktop switching still only manages settings. The
existing one-phone-per-code constraint remains. iPhone still requires the
installed Home Screen app.

The API accepts HTTPS Apple endpoints plus exact production hosts
`fcm.googleapis.com` (`/wp/`, `/fcm/send/`) and
`updates.push.services.mozilla.com` (`/wpush/`, `/push/`, `/v1/`). Endpoint/key
validation, subscription fingerprint CAS, profile isolation and worker v6 remain.
Unsupported/insecure browsers, denied permissions and provider connectivity
failures have actionable messages. Browser/system notification permission and
access to the provider are required; not every Android browser is supported.

Release `20261017-android-push-1792226291` preserves the actual prior release
`20261017-bot-clipboard-1792226158`, including its compact settings, branding
and clipboard modules. Backup:
`/opt/radar-webpush-test/backup-20261017-android-push-1792226291`.
Deployment used `deploy_settings.py --with-profiles`; only the push service
restarted, 2,639 other files and existing subscriptions/settings were preserved.
49 Python and 26 Node tests passed. An isolated real backend with simulated
Android browser APIs verified enable, transfer, destination settings and binding;
393px layout and live desktop settings/source status were checked. No production
test code or diagnostic push was created. Physical Android lock-screen delivery
has not been verified.

References: [Web Push subscription](https://web.dev/articles/push-notifications-subscribing-a-user),
[Chromium FCM endpoint change](https://chromium.googlesource.com/chromium/src/%2B/40644b8cf2b03be542976e7d1192c653e389c14e),
[Mozilla Autopush](https://mozilla-services.github.io/autopush-rs/).

## Defaults and behavior

2026-10-17: 合并通知改为最新消息在最上面。只在 render 层按原始时间倒序，
history/pending 保持原顺序；普通 worker 与声明式 fallback 共用 rows。
已定点发布 `20261017-newest-first-1792204285`，保留此前全站UI。
备份 `/opt/radar-webpush-test/backup-20261017-newest-first-1792204285` 包含旧 live.py、
PWA fallback 和发布摘要。只重启推送服务，接收服务不变；原订阅和设置保持。
回滚在维护锁内恢复上述两文件、切回 `20261017-ui-polish-1792203765` 并重启推送服务。
32 Python / 12 Node 测试通过；线上健康、源连接、订阅与排序函数已核验，
未额外发送测试通知，未声称亲眼验证 iPhone 锁屏。

- Real BOT messages, enabled, at most four entries per notification, newest first (updated 2026-10-17).
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

## Desktop push-code binding (2026-10-24)

The signed desktop state protocol explicitly sends `pushCode` (an eight-digit
code, or an empty string) together with `desktopRules: 1`. Empty means all
messages and cards are allowed; it does not read or apply the legacy owner's
rules. A valid code selects that profile's independent desktop, card and mobile
settings. The legacy code retains the existing root `desktop-rules.json`;
additional codes store desktop rules and journals beside their own `state.json`.
Existing mobile filters remain independent of the desktop and card channels.

Desktop code validation is read-only: it never pairs a phone, creates an access
token, moves a subscription, or changes the profile settings. Invalid codes and
service failures do not fall back to another profile or unrestricted delivery.
Successful repeated polling does not consume the failed-code attempt budget.

Bearer-authenticated desktop settings, card decisions and three-channel edits
now always use the token's own profile. Signed `coin-rules` with an explicit code
is likewise limited to that code's profile. The historical code-less management
operation still requires its existing explicit desktop capability. Merely
registering a reader does not give it global management or publisher privileges.
`pushBinding` responses report protocol/bound/canManage only, never the code or a
token. The new internal POST `/internal/desktop-binding` is loopback-only and
outside all public proxy routes; publisher forwards only after signature,
timestamp, replay and rate checks.

## Settings and ownership

2026-10-17 update: switching inside Android Chrome/Firefox or the installed
iPhone PWA also transfers that phone's subscription. Desktop switching selects only
the settings being managed and never remotely switches the phone. Each code's
settings and sequence stay intact. An occupied destination is rejected rather
than replacing another phone. A phone without a local subscription is prompted
to enable notifications after selecting the code.

`switch-subscription` authenticates the source bearer and destination token,
validates the exact source subscription, and uses ordered account locks plus a
private durable `subscription-transfer.json` journal. Recovery changes only
subscription/device fields. Requests are idempotent, and the destination is
paused until the configured phone reports a matching subscription. The browser
retains `radar-phone-switch` until server, worker and device synchronization
finish; uncertain responses can resume on reopening settings.

Worker v6 persists profile/token together, separates latest-message and receipt
storage by profile, and drops queued old-profile pushes. Old pages cannot
silently reconfigure it to their stale token. v6 uses ordinary Web Push so an
old-profile declarative OS fallback cannot bypass the worker's profile check;
existing v5 devices retain their previous delivery format until upgrading.

Released `20261017-phone-switch-1792207231` from
`20261017-switch-code-1792206410` with `deploy_settings.py --with-worker`.
Backups are in `/opt/radar-webpush-test/backup-20261017-phone-switch-1792207231`.
Only the push service restarted; existing subscriptions/settings and 2,634
other static files were preserved. 47 Python and 22 Node tests passed,
including transfer recovery, occupied destinations, cross-profile sequence and
receipt isolation. Browser acceptance used a real isolated backend with
simulated phone APIs: switch, reload and switch-back passed. Live 393/320px UI
passed; no extra production push or code creation and no physical iPhone
lock-screen validation were performed. The previous management-only phone
behavior described below is superseded by this update.

2026-10-17: **推送设置 → 通知与推送码 → 切换推送码** accepts another
eight-digit code and loads that profile's saved settings and revision. Saving
affects only the selected profile. Both status and binding must load before the
selection changes; failed switches preserve the previous selection and draft.
Successful switches replace unsaved inputs, as explained beside the input.
The selected management token persists as `radar-settings-token`; the original
`radar-test-token`, worker configuration, device telemetry and subscription stay
with the phone's original profile. Switching does not migrate notifications.
Return to the original code to manage this phone's notification permission.

Static release `20261017-switch-code-1792206410` preserves the concurrent compact
settings overlay from `20261017-compact-settings-1792206185`, all 2,634 unrelated
files and all production profile settings/subscriptions. No services restarted.
Backup: `/opt/radar-webpush-test/backup-20261017-switch-code-1792206410`.
All 16 Node settings/worker/protocol tests passed. Isolated real-backend browser
checks covered two-code editing, switching back, refresh persistence and failed
switch draft retention; live 393/320px layout checks passed. No production test
codes or extra pushes were created; physical iPhone behavior was not tested.

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

### Independent push plans and user-created codes (2026-10-17)

Production now starts `Profiles` from `profiles.py`. Bearer tokens resolve to one
`Profile` before **every** status, binding, settings, subscription, repair, device,
receipt, verification and stop operation. A caller cannot choose another plan by
adding a code/id to a request body. Same-code clients share that plan; different
codes have separate settings, revision, subscription, history, pending queue,
sequence, rate/backoff state and receipts. The source feed and VAPID credential
cache are shared; bounded worker tasks prevent one slow/failing sender from
serially blocking the next plan. A device endpoint can belong to only one code;
cross-code subscription/repair is rejected without altering either plan.

The legacy owner remains in `/var/lib/radar-webpush-test/state.json`, keeping its
exact token, subscription, sequence and settings. `profiles.json` is a versioned,
private registry; new accounts live in `profiles/<opaque-id>/state.json`. Do not
print these files, check them into Git, or restore an old sequence during rollback.
New codes use fresh defaults and do not inherit another plan's history or queue.

“新建推送码” is available to users behind the existing website access policy,
including those without a push code. POST `api/create-code` uses a random 128-bit
request ID for idempotent retries, produces an independent random eight-digit
code/token, and saves the plan before returning. Creation is capped at 20/hour
and 100 total plans; failures/retries cannot reset or modify existing plans.
Pair attempts are limited per visitor (trusted Cloudflare client IP at the
loopback proxy boundary), so one visitor's invalid guesses do not lock out other
visitors. Website access rules and the loopback-only listener remain unchanged.

On an unpaired client, creating a code also binds the new plan. On an already
paired client it displays the new code for another phone, preserving the current
token, worker, saved settings and any form draft. Creating a code does not subscribe
a phone or send a notification. The “开启通知” action is still user initiated.

Use `python web/push-test/deploy_settings.py --with-profiles` for this bundle.
It tests candidate modules, rehearses migration on private copies, verifies the
running-code baseline, backs up affected files and state, clones the current web
release, restarts only the push service, and verifies preserved bindings/settings.
Rollback restores code/static files without rewinding live state. The old
`--with-binding-api` flag is now an alias for this complete backend bundle.

Release `20261017-push-profiles-1792205891`: 44 Python and 12 worker/protocol tests
passed. Local browser acceptance used the real isolated backend with no sender:
two codes kept distinct settings, disabling one did not change the other, and
creation kept the current binding/draft. Production checks verified the original
token/subscription/settings/revision/device state, active source, anonymous 401,
the new button and 393/320px layout. No test push or extra production code was
created. Physical iPhone notification permission/display was not re-tested.

### Notification controls (2026-10-17)

BOT settings now always show an “开启通知” control and display the existing
owner's push code after pairing. The code is loaded only by the authenticated,
`Cache-Control: no-store` GET `api/binding` endpoint, not routine status responses
or static files. Existing paired devices do not need to enter the code again.
On an installed iPhone PWA, the button requests permission in the click gesture
and reuses or repairs the subscription through the existing fingerprint CAS.
Healthy devices show “通知已开启”; Safari and other browsers show installation
guidance. Enabling notifications preserves unsaved filter edits and does not
change the separate “接收消息” preference.

`python web/push-test/deploy_settings.py --with-binding-api` deploys this endpoint
and settings assets with backup/rollback, restarts only the push service, and
preserves subscription, settings, worker identity and the current website overlays.
Without that flag the script remains a static settings update.
Release `20261017-notification-controls-1792205078` passed 33 Python tests and
12 worker/protocol tests; browser checks covered permission/default/denied,
paired/unpaired and installed/browser states using synthetic fixtures, plus the
live authenticated code display and 393/320px layouts. No diagnostic push was
sent and no physical iPhone permission interaction was performed.

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
