---
id: reference.changelog
title: Changelog
category: reference
updated_at: 2026-08-04
summary: User-visible changes, newest first, grouped by release.
keywords: changelog releases history versions what changed news
---

Every user-visible change. Internal refactors are not listed.

## 2026-08-04 — About and Help

**Added**
- **About page** at `/about` — the problem, the three guarantees, the pipeline,
  why there is no domain code, and an explicit list of what does not work yet.
- **Help centre** at `/help` — every concept, control, chip, provider, decline
  reason and value type, with in-page search and a stable anchor per entry.
- Documentation coverage is now **enforced by a test**. A new endpoint,
  setting, provider, tier, decline reason or value type fails the build until it
  has a help entry.

## 2026-08-04 — Chat history that survives a session switch

**Added**
- Switching sessions and switching back now restores the transcript, the
  [tier chips](#ui.tier_chips), the [pipeline strip](#ui.pipeline_tracker) and
  the last retrieval — everything belonging to a turn swaps together.
- A reload returns to the session you were in, not the first in the list.
- `GET /sessions/{id}/turns` — [per-turn provenance](#api.sessions.turns):
  handle, parent, state version, disclosures. Deliberately no message text.

**Changed**
- Logging out now clears the chat transcripts stored in your browser. They are
  held client-side, and a shared machine must not hand them to the next person.
  See [where chat history is stored](#faq.transcript-storage).

**Known issues**
- A money value in a clause that names no recognised money concept defaults to
  `constraints.budget.max`. The vocabulary is literal, so `cost` is recognised
  and `costs` is not. See [the troubleshooting entry](#trouble.wrong-field).

## 2026-08-03 — Ollama split, and a longer demo

**Added**
- **Two Ollama cards** instead of one: [local](#provider.ollama), which is
  browser-direct and needs no key, and [remote](#provider.ollama_remote), which
  goes through our backend and requires one. Collapsing them into a single card
  had made the privacy difference invisible.
- **17-turn relief demo** with autoplay, a token sparkline, marked turns and an
  end card. See [the demo scenario](#demo.scenario).

**Fixed**
- Base URLs pasted from Ollama's own documentation (carrying a trailing `/api`
  or `/v1`) now normalise to the host instead of producing `/api/api/tags`.
- A 200 response carrying `{"error": "Unauthorized"}` is treated as the failure
  it is rather than as success.

## 2026-08-02 — Demo blockers

**Fixed**
- The Memory State panel renders **every** namespace the API returns, so
  [dynamic fields](#concept.dynamic-field) are visible instead of silently
  absent.
- Provider errors no longer leak raw payloads; each failure gets a readable,
  key-free message.
- An update now produces an acknowledgement that names what changed, rather
  than reporting a no-op — the model was only ever shown post-update state.
- [Restore a handle](#ui.restore_handle) from the console.

## 2026-08-01 — Open the extractor

**Added**
- **Dynamic fields**: a concept no registry entry claims becomes a first-class
  field instead of being quarantined. A kiln schedule or a load limit is
  remembered without anyone having written a rule for it.
- **Retraction** — [taking a value back](#concept.retraction) leaves the field
  genuinely empty.
- **Qualifier-aware updates**, so "push the end date" finds the end date.

**Changed**
- `_unmapped` now means "failed a guard", never "unfamiliar". See
  [decline](#concept.decline).

## 2026-07-31 — Fail closed

**Added**
- **Type-compatibility guard**: a value must pass a
  [type check](#concept.value-type) before it enters a field. `24 tonnes` can
  no longer be stored as twenty-four rupees.
- Grouped-number parsing (`1,240`, `1 240`) and rejection of degenerate values.

**Changed**
- Money now requires a **positive signal** — a symbol, a currency word, or a
  money noun. There is no default currency, because defaulting to one is how a
  bare number becomes a budget.

## 2026-07-30 — Canonical schema registry

**Added**
- One canonical path per concept, with aliases resolving onto it, enforced at
  the storage boundary. See [canonical path](#concept.canonical-path).
- Normalization to [base units](#concept.normalization), so `1,240 kg` and
  `1.24 tonnes` produce the same bytes and therefore the same
  [handle](#concept.handle).
