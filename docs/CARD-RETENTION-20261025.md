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

Deployment and installed-client verification are recorded after completion.
PR #46 remains open; no merge or formal GitHub Release is implied.
