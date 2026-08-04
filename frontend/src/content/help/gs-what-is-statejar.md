---
id: gs.what-is-statejar
title: What StateJar is for
category: getting-started
updated_at: 2026-08-04
summary: A memory layer that refuses to guess, records why it refused, and turns what it remembers into a portable handle.
keywords: intro overview start beginner what is
---

StateJar remembers facts from a conversation so a model does not have to be
told them again. That much is ordinary. Three things are not.

**It refuses to guess.** A value has to pass a type check before it is stored.
"Max load per container is 24 tonnes" is a quantity, so it cannot land in a
money field. When a value fails its check it is *declined*, not silently
coerced, and the decline is shown to you with a reason.

**One field holds one value.** When you change your mind, the old value moves
to history and the new one takes the field. The model is never shown both, so
it cannot answer from the version you replaced.

**What it remembers is portable.** Every state has a handle — a content address
computed from the state itself. The same state always produces the same handle.
Paste a handle into a new session, or a different model from a different
vendor, and you get that exact memory back.

The cost of this is that StateJar stores less than a system that guesses. That
is the trade being made deliberately: in a benefits application or a clinical
intake, a number remembered wrongly is worse than a number not remembered.

Start with [your first session](#gs.first-session).
