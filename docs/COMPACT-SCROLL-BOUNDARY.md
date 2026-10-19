# Compact message scrolling — v2026.10.19.4

After wheel, keyboard, scrollbar or automatic reading movement settles, the viewport aligns to the bottom edge of a compact message. The spread, action buttons and optional warning stay together. Alignment waits 140 ms and waits for a scrollbar drag or pending layout to finish. Messages taller than the viewport remain freely scrollable; the start and end of history remain reachable.

This release includes the previously local full-height message viewport prerequisite. It preserves the selected font size, continuous retained history, pinned-message area and manual resize behavior. Unrelated web changes and pending DEX/premium-summary work are excluded.

The release build runs a real WPF regression with 36 cases spanning two font sizes, two window heights, scrolling in both directions, automatic reading and optional warning lines, in addition to the existing build checks.
