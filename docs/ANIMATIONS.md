# StateJar — Per-Module GIF Animation Prompts (C)

Each module gets one self-contained design prompt. The shared visual system is defined once
below; every module prompt assumes it. Output: `animations/<module>.gif` (≤800px wide, ≤3 MB,
~12 fps), embedded in `README.md`.

## Shared visual system (prepend to every prompt)
> Style: minimalist Google-research-paper animation — clean white/cream background, thin 1.5px strokes,
> single accent color per actor, generous whitespace, no chrome. Palette: Anthropic-inspired —
> background `#F5F4EE` (cream), ink `#1F1E1D`, clay accent `#C96442`, sage `#6B8E7F`, muted gold `#D9A441`.
> Typography: a humanist sans (e.g. Inter / Söhne-like), small labels in lowercase. Motion: ease-in-out,
> 600-900ms per beat, hold 400ms on the key idea. No sound. Loop seamlessly. Export as GIF.

---

## 1. state-extraction
```
Animate "Structured State Extraction."
Scene 1 (0-2s): a chat bubble appears: "I'm Ayaan. I prefer email, not calls. Budget under ₹2000.
Haven't decided delivery time." typed out character-by-character.
Scene 2 (2-5s): from the bubble, colored chips detach and float right into labeled rows:
  • "name: Ayaan" (sage chip) → row FACTS
  • "contact_mode: email" (clay chip) → row PREFERENCES
  • "budget_inr_max: 2000" (gold chip) → row CONSTRAINTS
  • "delivery_time: ?" (dashed outline chip) → row UNRESOLVED
Scene 3 (5-6s): rows settle into a tidy JSON card titled "state". Hold.
Label bottom-center: "facts · preferences · constraints · unresolved".
```

## 2. canonical-normalization
```
Animate "Canonical Normalization — identical meaning, same state."
Scene 1 (0-2s): two cards slide in side by side.
  Card A: { "constraints": {"budget": 2000}, "facts": {"name": "Ayaan"} }
  Card B: { "facts": {"name":"Ayaan"}, "constraints": {"budget": 2000} }
Scene 2 (2-4s): keys in each card animate sorting alphabetically (swap positions with a soft slide),
  whitespace collapses, a "v1" schema tag snaps onto both.
Scene 3 (4-6s): both cards morph into one identical card in the center, a checkmark appears.
Label: "order & wording don't matter → one canonical form".
```

## 3. handle-generation
```
Animate "Deterministic State Handle."
Scene 1 (0-2s): the canonical JSON card sits center. Three labeled pills attach below it:
  [canonical_state] [schema_v1] [norm_v1].
Scene 2 (2-4s): the pills' contents stream into a small "SHA-256" gear box; the box spins briefly.
Scene 3 (4-6s): a single fingerprint-style code emits from the box: "shm_8f3a9c…d21".
  A lock icon clicks onto it. Hold.
Label: "SHA256(canonical_state + schema_v1 + norm_v1)".
```

## 4. persistent-storage
```
Animate "Handle-Indexed Persistent Storage."
Scene 1 (0-2s): the handle "shm_8f3a…" sits on the left; on the right a MySQL database cylinder.
Scene 2 (2-4s): the handle acts as a key — it slides into the cylinder's index slot; the full state
  JSON card drops into a row behind it. A small "outside context window" bracket encloses the DB,
  clearly separate from a faded "LLM context" box on the far left.
Scene 3 (4-5s): a second handle "shm_0000" shows as parent_handle, linked by a thin line.
Label: "full state stored by handle — outside the model's context".
```

## 5. minimum-sufficient-retrieval
```
Animate "Minimum-Sufficient Retrieval."
Scene 1 (0-2s): a query bubble: "Book my delivery with my usual preferences."
Scene 2 (2-4s): the full state card is shown faded with many fields; three fields highlight
  (pulse clay): preferences.contact_mode, constraints.budget_inr_max, unresolved.delivery_time.
  The other fields dim and a small scissors icon trims them away.
Scene 3 (4-6s): only the three highlighted fields remain in a compact card that flies up toward a
  small "LLM" node alongside a frozen "system prompt" card.
Label: "only the subset needed — nothing more".
```

## 6. versioning
```
Animate "Versioned State Evolution."
Scene 1 (0-2s): handle "shm_A" card with state {budget: 2000}.
Scene 2 (2-4s): user bubble: "Budget is now under ₹2500." A new card "shm_B" forms, state {budget: 2500}.
Scene 3 (4-6s): shm_B links to shm_A via a "parent_handle" arrow; shm_A stays unchanged (a small
  "preserved" pin). A vertical timeline grows downward: A → B.
Label: "new handle on update — old versions never overwritten".
```

## 7. conflict-preservation
```
Animate "Conflict Preservation."
Scene 1 (0-2s): earlier preference chip "contact_mode: email" (sage).
Scene 2 (2-4s): new user bubble: "Call me only." A "contact_mode: call" chip (clay) appears.
Scene 3 (4-6s): instead of replacing, both stack into a "conflicts" sub-card:
  { field: contact_mode, old: email, new: call, ts }. A warning glyph marks it; nothing is deleted.
Label: "contradictions kept as first-class state — not overwritten".
```

## 8. audit-replay
```
Animate "Audit & Replay Provenance."
Scene 1 (0-2s): a response bubble to the user; a dotted "provenance" line trails from it.
Scene 2 (2-5s): the line connects to an audit-log row that fills in field by field:
  request_id: req_102 · input_query: "Book my delivery" · handle_used: shm_B ·
  subset_keys: [contact_mode, budget_inr_max, delivery_time] · schema_v1 · norm_v1 · ts.
Scene 3 (5-6s): a "replay" button pulses; pressing it re-runs the same subset → same response.
Label: "which handle & subset shaped each answer — replayable".
```

## 9. graph-rag-traversal
```
Animate "Graph-RAG Tree Traversal — the speed-of-light path."
Scene 1 (0-2s): a query bubble: "Order it again." GLiNER2 chip tags entities: [delivery, preference].
Scene 2 (2-5s): a knowledge graph of nodes (FACTS, PREFERENCES, CONSTRAINTS, UNRESOLVED) with typed
  edges fades in. The extracted entity tags light up two nodes; a clay pulse travels along edges from
  those nodes to only the connected branches; un-reached nodes stay dim.
Scene 3 (5-7s): the reached nodes' values gather into the compact subset card and fly to the LLM with
  the frozen system prompt. Un-reached graph remains faint in the background.
Label: "extract → find node → traverse branch → retrieve only what's relevant".
```

## 10. playground-chat
```
Animate "Playground — live memory view."
Scene 1 (0-2s): a two-pane app shell (Anthropic cream theme). Left: chat. Right: "Live Memory" panel.
Scene 2 (2-5s): user types "I prefer WhatsApp updates, budget under ₹1500." In the right panel, a
  state card builds in real time: preferences.contact_mode=whatsapp, constraints.budget=1500. A handle
  chip "shm_…" updates; the Graph-RAG mini-tree adds two nodes.
Scene 3 (5-7s): user asks "Order it again." Right panel shows the subset highlighting (clay pulse) +
  the trimmed card sent to the model. A "session reset" pill sits top-right.
Label: "chat on the left, memory forming on the right — in real time".
```

## Rendering checklist (per GIF)
- [ ] Reads the prompt above + the shared visual system.
- [ ] Frames assembled at ~12 fps, ≤800px wide, ≤3 MB.
- [ ] Visually matches the module's **real** behavior (rule 4 — no misleading animation).
- [ ] Saved to `animations/<module>.gif` and embedded in `README.md`.