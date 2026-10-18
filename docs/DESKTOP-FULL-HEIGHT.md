# Desktop full-height message history

Version: v2026.10.18.3 (2026-10-18)

The right-hand panel previously mounted only three ordinary messages and fitted its height to short summaries. It now uses the monitor work area height in automatic mode and mounts the bounded session history (at most 100 messages). The viewport determines how many messages fit; overflow scrolls without reducing the user's chosen font size. Manual height resizing remains supported; the home button restores automatic full height.

Compact messages no longer reserve a separate Full Text expander row. Clicking the message surface toggles the original body; Enter/Space also works on the focused message. Action buttons and links retain their original targets and do not toggle the body. The View Radar action is aligned to the far right of the spread row, as requested. Actions without a spread remain below their summary.

Initial connection and reconnect align the latest history with the bottom. Subsequent arrivals and oldest-message eviction preserve the reader's visible anchor. The pinned message retains a bounded, separately scrollable region. The existing reading interval and opportunity board remain in place.

## Verification

- 420 core checks passed.
- Complete current WPF smoke suite passed after updating obsolete three-slot/font-shrinking expectations to the new policy.
- Final compact-summary fixture passed four message forms, eight exact action URLs, surface/keyboard expansion, and far-right button geometry.
- Final full-height fixture passed 11 checks, including >3 visible real fixture messages, latest-at-bottom, unchanged font, anchor retention, bounded history, manual resize, narrow width, long pin, and return to automatic height. Synthetic rendering showed 22 of 30 retained messages at font size 13.
- Cloud-window fixture passed initial/reconnect placement, actual five-second timer progression, and pinned replacement retention.
- Opportunity column-height fixture passed six checks.
- Installed through the existing updater with rollback backup. Healthy receipt and runtime diagnostics confirmed v2026.10.18.3, Connected, 11 visible ordinary messages, full work-area height, font 13, five-second reading, and pinned content. Private storage files, pointer and preference fields matched the pre-update baseline.

Visual verification uses isolated WPF rendering with fictional messages. Live installation was verified by health receipt and application diagnostics, not a live desktop screenshot. Physical multi-monitor/DPI transitions, dragging, and audible output were not manually tested. No production test notifications were sent.
