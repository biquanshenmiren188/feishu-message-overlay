# Collapse DEX messages with instrument labels

2026-10-18, desktop v2026.10.18.9.

DEX entry parsing previously required `多 Bitget / 空 OKX` exactly. Messages containing `多 Bitget 现货 / 空 OKX 合约` failed to produce a summary, causing the desktop plain-text renderer to display the complete body. Both web and desktop parsers now accept the optional known labels 现货, 合约 and 永续 after either exchange name. The explicit message mode still determines SF/FS/FF; no mode, amount or risk data is inferred from the labels.

The compact display keeps instrument, mode, route, P rank, opening spread and quality. Thresholds and configuration stay in the original body, available on click. Original content and URLs remain intact. Existing rank-first titles and inline radar actions are preserved.

Validation: 27 web summary tests passed; 71 generated parity fixtures and 450 core checks passed. Cases include spot/futures in both directions, perpetual legs, mixed labelled/unlabelled legs, negative values, suffixes and multi-entry values. WPF checks reproduced a plain IncomingMessage without card metadata, confirmed it starts collapsed, and verified expansion, collapse and exact original body retention; the existing four-card/eight-URL checks also passed. Browser replay showed the two-line summary and complete original content on click.

Web release `20261017-summary-risk-1792305392` replaces only the active summary regex in `bot-summary-b57d07da936d.js`, preserves 2,878 other files and service PIDs, and synchronizes the PWA fallback. Desktop updater health receipt and diagnostics confirmed v2026.10.18.9, Connected, full-height, font 13, five-second reading, and unchanged preference fields. WPF visual evidence uses a fictional TOKEN reproduction; no live desktop screenshot was taken.
