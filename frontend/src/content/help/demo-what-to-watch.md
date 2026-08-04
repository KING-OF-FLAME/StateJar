---
id: demo.what-to-watch
title: The 17-turn demo: what to watch
category: demo
updated_at: 2026-08-04
summary: Four things on the right-hand side, and what each proves.
keywords: demo watch panels sparkline handle savings controls
---

While it runs, the right-hand panels are doing the actual argument.

1. **Memory State.** Field count grows, and on turns 8, 11 and 13 it changes
   rather than grows. Nothing is ever duplicated.
2. **The handle.** It changes on every turn that changed the state, and only
   then. A repeated fact does not move it — see
   [reinforcement](#concept.reinforcement).
3. **The sparkline and the savings line.** Tokens sent per turn against a
   **full-transcript replay** baseline. Early turns can show *more* than
   replay, and the demo says so on screen instead of hiding them — with three
   short messages there is nothing to save. The gap opens as the transcript
   grows. See [token savings](#concept.token-savings).
4. **The end card.** The final handle. Copy it and
   [restore it](#ui.restore_handle) in a fresh session to prove the whole
   seventeen-turn memory travels as one string.

**Controls.** Play, Pause, Resume, Restart, Skip to end. Skip waits for the
in-flight turn rather than abandoning it.
