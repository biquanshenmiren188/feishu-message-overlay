# Rank-first titles and bottom-right message actions

2026-10-18; desktop v2026.10.18.7.

Web and desktop ordinary message titles move the existing R rank and adjacent percentage to the front, preserving rank suffixes, signs and precision. Titles without that pair retain their order. This is display-only: original message content, URLs and signal parsing remain unchanged.

Every original message action now appears together at the bottom-right, including pinned messages and expanded originals. This supersedes the earlier spread-row placement. The web no longer renders the Full Text hint. Clicking a message opens its original content; clicking an action follows its original link without also opening the message. Keyboard actions remain available. Desktop titles retain near-black extra-bold styling; spread text remains regular weight.

Validation: four WPF summary forms/eight original URL actions, title placement, bottom-right action geometry and click/keyboard expansion passed. The full-height desktop fixture passed all 11 checks, including narrow width, preferred font, retained history and stable reading position. Browser candidate checks verified action alignment and link isolation; a 393px iframe preview was visually inspected. Five title-ordering cases covered suffixes, signs, precision and unrelated titles. Live browser verification confirmed rank-first titles, no Full Text hints, and bottom-right action rows.

Web deployment cloned the inspected current release, preserved 2,874 unrelated files and service PIDs, added immutable assets, and synchronized the PWA fallback. Release: `20261017-summary-risk-1792302323` (publisher retains its historical date prefix). Assets: `bot-summary-313ff3d07145.js` and `summary-risk-a384c2bc5085.css` under `performance-20261017/`.

Desktop installation used the existing rollback-capable updater. Healthy receipt and application diagnostics confirmed v2026.10.18.7, Connected, full work-area height, 16 visible ordinary messages at the checked instant, font 13 and five-second reading. Preference fields matched the pre-update baseline. Live desktop visual capture and physical iPhone validation were not performed.

`web/robot-push/prepare_message_actions.py` prepares the inspected bundle patch, immutable asset manifest and isolated fictional replay. Only candidate manifest files are published by `deploy_summary.py`; replay fixtures must never be deployed.
