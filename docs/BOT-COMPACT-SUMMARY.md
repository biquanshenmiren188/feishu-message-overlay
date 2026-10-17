# BOT compact messages — 2026-10-17

The list displays a compact heading on desktop and mobile. Ordinary opportunities replace `V2收敛` with the observed buy-to-sell exchange route, e.g. `EPIC｜SF｜GT→BG｜R0 +0.37%`. Direction, metrics, fees and generic previews are hidden in the list; clicking or pressing Enter/Space opens the unchanged original message.

Strong signals show `强信号｜EPIC｜3组` and one row per observed route, rank, type and net mean percentage. The group count uses the original declared count, falling back to parsed rows. Exchange abbreviations are shared with warning text. The arrow is `→`.

Warnings retain instrument, event and effective date/time, wrap fully and deduplicate repeated sentences. Empty/unknown placeholders do not create a warning row. Missing transfer data never implies all-open status.

Production was patched from the active static bundle, preserving the separately deployed mobile scroll fix, clipboard handling, worker identity, settings and brand assets. `prepare_summary.mjs` performs bounded replacements and fails when expected current bundle shapes differ. Its replay output is test-only and is not in the release manifest. `deploy_summary.py` validates the current release, all inspected hashes and the PWA fallback under the deployment lock; it clones the current release and preserves unrelated assets and service PIDs.

Latest release: `20261017-summary-risk-1792230044`, based on `20261017-summary-risk-1792229879`; 2,723 existing files preserved, no service restart. The preceding summary release was based on `20261017-mobile-scroll-1792229554`.

Validation: 98 existing/new web tests passed for the compact layout and strong-signal parsing, followed by 16 summary tests after adding the count. Chrome 393px/320px replay checked complete warning text, hidden placeholder rows, no horizontal overflow and full-text opening; desktop opening and live strong-signal data were verified. No notification was sent. This is browser responsive validation, not physical iPhone verification.

Known inherited behavior outside this change: unmarked warning keyword scanning can still interpret configuration text such as “价格最大延迟” as a warning; untitled custom message types use the generic heading and remain readable through full text.
