---
id: concept.handle
title: Handle
category: concepts
updated_at: 2026-08-04
summary: A content address for one exact state: same bytes in, same handle out.
keywords: handle hash address shm content addressed portable
---

**Definition.** A short string, `shm_` followed by a hash, that addresses one exact state. It is computed from the state's own canonical bytes.

**Why it exists.** So memory can be moved and verified. If the address is derived from the content, then an address that resolves proves the content was not altered, and the same content anywhere produces the same address.

**Where you see it.** Under the tabs in the Playground, with a copy button. Also on every row of the Handles tab and in every audit entry.

**Worked example.** Ingest a fact and note the handle. Ingest the identical fact into a fresh session — the same handle comes back, because the state is the same. Change one value and it changes completely.

**Common misunderstanding.** That a handle is an id the server made up, like a row number. It is not: nothing assigns it. It is what the state hashes to, so two servers that never met agree on it.
