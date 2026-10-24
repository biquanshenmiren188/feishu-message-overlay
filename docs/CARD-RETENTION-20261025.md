# Shared 30-second expired card retention

The user requires both the website and desktop to retain an expired opportunity
for 30 seconds. Previously each client started its own missing-card timer, and
refreshing the website discarded the historical card while the desktop kept it.

The existing BasisPulse mirror now publishes recently retired cards with a shared
`expiredAt` timestamp based on the source snapshot (bounded by `validUntil`).
It restores its prior cache on restart and preserves known active cards during
incomplete snapshots. Both renderers load that history and remove it at the same
30-second deadline. Refresh, delayed delivery and scrolling cannot restart or
extend the timer. Active re-entry replaces the retired card for that pair.
Card policy evaluation includes this retained history so blocking still applies.
No phone subscription, push rule or desktop preference is changed by deployment.

Validation:

- Publisher Python suite: 17 tests passed.
- Web Push Python suite: 95 tests passed.
- Browser/Node suites: 202 tests passed, including source and the patched live
  renderer, delayed arrival, refresh, scrolling, exact expiry and blocked cards.
- Self-contained Windows build: 590 core checks, WPF contracts and all four
  updater scenarios passed; complete recovery contracts passed. An initial run
  encountered an unrelated clipboard payload failure; the full retry passed.
- v2026.10.25.1 archive: all 656 manifest files verified. SHA-256:
  `dff7e653e47bda7d43ca0fc26e6f17c56688d1a0951031a944ed140c7daa86a8`.
- GitHub hosted CI was previously blocked before running by account billing;
  these are local validation results, not a hosted CI pass.

Publication uses the existing static release guard and exact live bundle hash.
It clones the current website, preserving other files and the existing scroll
and clipboard patches. Only `basispulse` and `radar-webpush-test` restart; the
robot publisher and unrelated services remain running. User settings and
bindings are compared before/after. Rollback restores code, never user data.

Published source: `d2b587beacecec88f78f8b4806e019b5347de8ec`.
Static release: `20261025-card-retention-1792858266-82769a`, cloned from the
latest concurrently advanced `20261024-same-period-1792858252` release.
All 3333 non-target files were preserved. BOT bundle:
`performance-20261017/bot-cards-70a0144354ee.js`. Both lifecycle services and
the robot publisher are healthy; rules, subscriptions, bindings and unrelated
service PIDs were unchanged. The server emits `retentionSeconds: 30`.
An additional 23 isolated candidate tests passed on the server before switching.

The user exited the previous client through its tray menu. The built-in updater
installed v2026.10.25.1 and returned a successful health receipt. All 656 files
match the candidate, both cloud and rules connections are healthy, the window
is visible in the original interactive session, recovery is watching, and the
process is outside the launcher job. Private-file hashes, storage pointer and
all original preference fields are preserved.

Authorized Chrome verified the live card panel and bound-policy status after
publication. The live snapshot at verification had no recently retired cards;
the exact 30-second boundaries, delayed refresh and scrolling were verified by
the isolated source/live-renderer and Windows contracts, not fabricated live
events or changes to the user's actual rules.
PR #46 remains open; no merge or formal GitHub Release is implied.
