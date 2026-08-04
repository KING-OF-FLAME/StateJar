# Known issues

Behaviour that is wrong, understood, and deliberately not fixed yet. Each entry
says what actually happens, why it happens, and what a fix would have to touch —
so nobody re-diagnoses it from scratch on a demo morning.

---

## 1. Unclaimed money defaults to `constraints.budget.max`

**What happens.** A clause containing money that neither vocabulary in
`app/memory/rules.py` recognises is stored as the budget, whatever it was
actually about.

**Why.** Routing is a two-list decision in `names_another_money_concept()`
(`rules.py:173`):

- `_BUDGET_WORD` (`rules.py:159`) — `budget · price · cost · spend · afford ·
  paisa · paise`. A match means "this money *is* the budget", and it wins even
  when another money word is also present ("rent budget is 35000").
- `_OTHER_MONEY_CONCEPT` (`rules.py:165`) — `insured · insurance · premium ·
  turnover · revenue · salary · wage(s) · invoice · rent · deposit · emi ·
  instalment/installment · refund · valuation · payout · claim · fine ·
  penalty · tax · gst · duty · freight · commission`. A match means "this money
  belongs to something else", and it keeps its own field.

A clause in **neither** list falls through to the default destination, which is
the budget. The failure is silent: nothing is quarantined and no conflict is
raised, so the panel shows a confident wrong number.

**The word-boundary trap.** The lists are matched with `\b…\b`, so they are
literal, not stemmed. Verified:

| word | `_BUDGET_WORD` | `_OTHER_MONEY_CONCEPT` |
|---|---|---|
| `budget`, `cost`, `price`, `spend`, `afford` | ✅ | ❌ |
| `costs`, `prices`, `costing`, `allowance` | ❌ | ❌ |

`cost` routes; `costs` does not. Two demo turns hit this — they matched
*neither* list and landed on the default. The earlier explanation that "the
budget word won" was wrong; nothing won, the default fired.

**Why it is not fixed.** Adding plurals to `_BUDGET_WORD` widens what claims the
budget slot and would need the full golden battery re-run to show it does not
misroute something else. The honest fix is not a longer list at all — it is
making an unclaimed money value *fail closed* into `_unmapped` instead of
guessing a destination, which is a change to routing behaviour and therefore
outside the current freeze.

**What a fix touches.** `rules.py` (both vocabularies plus the fallback branch),
the fail-closed guard, and the golden corpus.

---

## 2. Chat transcripts live only in the browser

**Not a defect — a consequence of the claim**, recorded here because it looks
like one from the outside.

StateJar never stores a raw transcript server-side (patent module 5;
`storage._assert_no_transcript` refuses them at write time). So:

- History is **per browser**. Sign in on another device and the *memory* is all
  there; the conversation is not, because only state travels.
- Clearing site data clears the transcript. The state survives.
- Logging out wipes every stored transcript in that browser — a shared machine
  must not hand the next person the last conversation.

The server's half of a session's history is provenance, not words:
`GET /api/v1/sessions/{session_id}/turns` returns, per turn, the handle that was
current, its parent, the state version, and what was disclosed from it. It is
explicitly not a transcript endpoint and says so in its own response
(`contains_message_text: false`).

Implementation: `frontend/src/lib/transcript.js`.

---

## 3. Tier 3 needs configuration that the demo accounts did not have

The 17-turn relief demo and the seven replaced turns were measured with
**rules only** — `{"rules": "ok", "gliner2": "skipped", "llm": "skipped"}`, and
zero `provider_keys` rows on the QA accounts. Those runs say nothing about tier
3's behaviour. Treat the seven turn replacements as unvalidated until they are
re-run on an instance with a provider key present.
