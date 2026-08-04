---
id: decline.user_rejected
title: Conflict: user rejected X in favour of Y
category: reference
updated_at: 2026-08-04
summary: You explicitly swapped one option for another, and both are recorded.
keywords: user rejected conflict instead swap contact mode
---

**What it means.** You did not merely change a value — you rejected one option
and chose another. `Call me instead of emailing`.

**Not a decline.** The chosen value **is** stored. This is a
[conflict](#concept.conflict) record explaining how the field got its value,
written as `user rejected email in favour of phone`.

**Why record it.** An explicit rejection carries information a plain update
does not: it says the other option was considered and refused, which is worth
knowing before suggesting it again.

**Where you see it.** The `conflicts` list in Memory State.
