# Web session history — 2026-10-11

Current static release: `/opt/funding-radar-web/releases/20261011-web-session-history`; active module namespace: `robot-push/web-session-20261011`. This section supersedes historical retention and render behavior below.

- Keep the latest 100 accepted ordinary messages in the current page session, with an independent latest pin. Idle time does not evict accepted messages. Refresh starts a new session and reloads the server's recent feed; this is not persistent history. Incoming stale messages remain rejected.
- Preserve the existing scroll rail, reading cadence, mobile summaries and layout; no History button. Unchanged feed content does not rebuild or reposition the message list.
- Reuse parsed snapshots on genuine HTTP 304 responses. The shared worker sends a small unchanged notification instead of repeatedly cloning the full snapshot. Existing delta requests, shared polling across visible tabs, hidden-page suspension and error backoff remain enabled.
- Opportunity cards retain the desktop lifecycle: stale after 20 seconds, expired cards retained for 30 seconds. Status/age updates run locally without extra HTTP requests; normal values remain limited to the existing 10-second display cadence. Unchanged cards retain their DOM nodes.

Validation: all 83 Node web tests passed. Synthetic browser fixtures at desktop and 390px widths passed 10 checks each, including idle-day retention, original history keyboard navigation, independent pin, bounded nodes, unchanged DOM preservation, stale/expired transitions and no horizontal overflow. The live authenticated page loaded the new namespace, showed the updated retention notice, shared transport, HTTP 304 and delta counters. Browser-extension errors were unrelated to page modules. This is not physical mobile-device testing.

Deployment copied the previous release, verified baseline and candidate SHA256 values, then atomically switched the current symlink. Backup: `/opt/funding-radar-web/backups/20261011-web-session-history`; previous target: `/opt/funding-radar-web/releases/20261009-push-low-traffic-v2`. No receiver restart, message-data mutation, authentication or network-security change was required.

---

> 2026-10-10：当前 Windows 安装和云端读者授权请看 [CLOUD-SETUP.md](../../CLOUD-SETUP.md)。本文件下面的逐项哈希一致结论仅适用于当时部署；新增只读授权后 server.py 已变化，旧 source-hashes 不能作为当前整体一致的证明。

# Deployment reconciliation — 2026-10-03（历史记录）

Current web release: carousel-20261003m. Mobile five ordinary summaries plus independent pin; desktop three ordinary full-text cards plus independent pin. Static files page.js, carousel.js, style.css, index.html, feed-color.js exactly match the running site. page.mjs mirrors page.js for source tooling; index.html loads page.js. demo.js is the non-private fixture dependency. Do not restore the older page.mjs-only deployment recipe.

The seven receiver source hashes in deployment-source-hashes.json were read from the existing official cloud terminal and all match this source tree. The prior concern about an unknown deployed receiver baseline is resolved. No server configuration, credential files, message database or third-party audio is included.

Cloud is the sole Feishu receiver. Desktop cloud mode does not start a local SDK fallback. Optional whitelisted headerTone preserves card header.template; missing/unknown metadata is grey. Old records with discarded color cannot be reconstructed.

Web: all controls left; plain latest button always present; global history scroll; no inner card scrolling or automatic internal pagination. Five-second dwell and ten-second manual idle are unchanged. Three regular plus independent pinned one; bounded fit may reach readable minimum with global scrolling for excessive content. Desktop: matching color receiver/rendering fix, pale header with colored opaque text.

Evidence: live assets match; 3 natural blue records rendered using production web assets with foreground #3E69B8/background #E8EDF6 in an isolated browser, without writing their bodies. Synthetic PC/390px geometry passes. Desktop running exe matches the built color candidate, single instance/cloud Connected/5s/audio configured; sound currently off and preserved. Existing real WPF synthetic blue/DispatcherTimer tests passed. Natural red and direct production desktop blue visual comparison remain unverified; a 390px test is not iPhone/WeChat hardware acceptance.

Third-party Jin10 WAV deliberately excluded. Provision the user's existing authorized audio separately; never claim the source archive includes it.

## Bounded performance follow-up
Only page.js and index.html changed from g to h; cloud service, desktop executable, timers, colors and interaction rules unchanged. Static backup: /opt/robot-push/backups/ui-conditional-20261003.
Observed repeated unchanged feed responses: 38,470 body bytes each. Existing server ETag probe: 35,211-byte baseline -> HTTP304, 0 body bytes (response headers still transferred). h sends If-None-Match, reuses one in-memory snapshot on 304, and still performs expiry, freshness and dedup checks. No persistent browser message cache added. Snapshot older than45s clears validator to force a fresh request next cycle. No server header/security changes.
Isolated production-assets regression: 1140px/390px passes geometry, history/latest, 5s/10s, 200/304/error recovery, 3+pin and unique containers. Physical iPhone acceptance remains unverified.
Layout baseline: over15.4s unchanged input at both widths, 3 polling render calls, zero additional card builds and zero additional fit measure passes; existing key cache works. 30 synthetic scroll dispatches caused no card builds/fit passes in this fitted fixture. This is operation-count evidence, not CPU milliseconds or native scrolling latency. No extra layout cache or redraw skipping added because benefit was not demonstrated enough to justify invalidation risks.

2026-10-03 i: new visits select latest three on first nonempty snapshot; initial placement canceled by manual interaction; later snapshots do not pull history. Independent pin, existing timers and audio unchanged. Natural first-open proof and six production-resource fixture combinations passed.

2026-10-03 j: saved sound-on gets silent resume and trusted page gesture unlock. Sound-off remains off; no unlock test playback. Deployed mock-policy tests passed; physical iPhone permission behavior unverified.


## Release k — batch reading and mobile summaries

- Every configured cycle (default 5 seconds), admit up to two pending ordinary messages, one if only one is pending, none if empty. The visible window contains at most three admitted ordinary messages plus one independent pin. A second message received at 4.9 seconds joins the first at the 5-second boundary. Arrivals/polls do not reset an active deadline. At idle tail no reading timer runs; the next arrival uses the next existing cycle boundary. Background recovery starts a fresh cycle without catch-up bursts.
- Only actual wheel/key/thumb/touch movement that changes the reading position pauses auto. At last actual movement +10 seconds, admit up to two pending messages immediately. The next batch is eligible +5 seconds later at the default setting. If none are pending, keep the view unchanged and use the next normal cycle for subsequent arrivals. Plain clicks, taps, audio unlock, layout and programmatic scroll do not create this pause.
- Mobile <=640px: deterministic summaries, pin + three ordinary cards, original title/tone/time and observed direction/metrics/fees, explicit unavailable/unknown/warning states. Missing fields are not fabricated. Unknown types show the original prefix. Full original text/actions remain in a separate scrollable dialog snapshot. Reading the dialog freezes list presentation/timing, not receipt; return preserves the range/scroll and remaining cycle. No model API, persistent body cache, permission or audio change.
- Mobile explanatory footer hidden; desktop footer retained. Automatic positioning starts at the top of its three-card range rather than obscuring the first card under a sticky pin. Phone pin is a normal flow summary. Desktop full original body unchanged.
- Validation evidence: 19 reader +4 extractor tests; actual Chromium DOM/timer/scroll fixtures at1140x844,390x844,390x568. 5 pending ->2/2/1,4.9-second arrival pair, genuine manual range movement/10s recovery, click/tap nonpause, latest/empty snapshot/history, full-detail stable snapshot/return, safe links, offline/304/dedup and audio policy mocks passed. Timers use Chromium virtual time; this is not physical iPhone/WeChat or native audio permission acceptance. Very narrow/short screens or unusually long summary fields may require outer scrolling; no four internal scrollers or discarded originals.
- No Windows executable, receiver service, main funding-query site, credentials, retention policy or third-party audio changes in this release.


Deployment backup: /opt/robot-push/backups/ui-batch-summary-20261003. The first normal-admin attempt failed creating the backup directory before any writes; the same guarded static deployment then succeeded using existing noninteractive sudo. No security settings changed. Five public asset SHA256 values match local LF-normalized source. Nine post-deploy production-resource Chromium fixture cases passed. Source metadata at15:10:35UTC: Connected=true, updated15:10:33.610UTC,56 ordinary/pin present; bodies not recorded. Physical mobile browser acceptance remains unverified.

The authoritative current behavior is this release section; dated i/j and earlier evidence above describes historical versions. Manual recovery, batch admission and phone summaries supersede prior one-ID-per-cycle/full-phone-original descriptions.


## l — exact manual-idle recovery
Only the manual recovery branch in carousel.js changed; page/index references carry the new version. Backup: /opt/robot-push/backups/ui-manual-resume-20261003. T is the last real manual or inertial scroll: T+9.999s unchanged; T+10s admits min(2,pending); T+15s admits the next batch. More movement resets T; ordinary clicks do not. Zero pending at recovery does not move the view and resumes the normal5s cadence. No extra5s is added before the first batch.
20 clock-injected reader tests pass. Inertia browser fixtures use16ms controlled animation frames and virtual time: unpaced headless virtual time alone can leave rAF pending. This is not physical iPhone/WeChat validation. The prior interrupted deployment was confirmed unexecuted (old k hashes); its already-pasted command was then executed once, and all three l asset hashes matched. No second payload submission, receiver restart, summary change, sound change or Windows app change.


## m — six mobile cards, global history rail, backdrop close
Mobile<=640px capacity is5 ordinary +1 pin (actual count only); desktop remains3+1. At each displayed range or viewport change, cards are measured at final width, at13px summary text, and spare vertical height is distributed across actual cards. Visual viewport and safe-area bottom are accounted for. Tested390x844/680/568: available heights750/586/474px, six-card totals equal those heights, final border gap1px. At390x480, content minimum~471px exceeds386px available; the sole outer scroller keeps the full cards accessible instead of shrinking text/cropping warnings. No per-card scrollbar.
One persistent global history rail combines real range index and real within-range scroll position. Desktop rail is draggable/keyboard operable; mobile rail is passive and does not intercept touch. Because only3/5 history cards exist in DOM, a native scrollbar alone cannot represent earlier history: the unified rail replaces its visual, not the scroll container. At no history/no overflow the rail is hidden; interaction darkens it, idle remains visible. Range/count and current-range percentage are exposed accessibly, not fabricated progress.
Clicking the full-detail backdrop closes back to the same message list/position, not the funding homepage. Pointer origin/end and8px click movement threshold prevent inside-to-outside drags from closing; body/link clicks remain inside; Escape/return remain available. Focus restores to the original card or board if a responsive capacity change removed that card. No click-through or new manual-idle pause.
31 core reader tests passed; candidate browser cases cover5 viewport/layout/backdrop,2 insufficient/empty,4 batch timing,5 audio policy mocks. Public m files are hash-verified and production-resource geometry/backdrop/batch fixtures pass. Browser testing is isolated Chromium with synthetic data/virtual time; not physical iPhone/WeChat or native touch/audio permission verification. Backup:/opt/robot-push/backups/ui-six-scroll-20261003. No receiver restart, financial extraction expansion, main funding-site or Windows app change.
