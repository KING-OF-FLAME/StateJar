---
id: gs.first-handle-restore
title: Your first handle restore
category: getting-started
updated_at: 2026-08-04
summary: Copy a handle from one session and open that exact memory in another.
keywords: restore handle portable cross session copy paste
---

This is the demonstration that tends to convince people, and it takes about
twenty seconds.

1. In a session with some state, click the **copy button** beside the handle
   line. You now have something like `shm_a5f9911c29fabe25…` on your clipboard.
2. Click **+ New session**. The Memory State panel is empty — a new session
   starts with no memory.
3. Paste the handle into the **restore** box in the toolbar and submit.
4. The state comes back exactly as it was. Same fields, same values, same
   handle.

What just happened: the handle is a content address. Restoring re-derives the
handle from the stored state and refuses if the two disagree, so a restore that
succeeds is proof the bytes were not altered.

The same handle works across models and vendors. Restore it in a session using
a local Ollama model and you get the identical state you built with a hosted
one — because the state is data, not a vendor's memory feature.

What a handle does **not** carry: the conversation. See
[why transcripts are not stored](#faq.transcript-storage).
