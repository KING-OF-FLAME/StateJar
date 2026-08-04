---
id: reference.glossary
title: Glossary
category: reference
updated_at: 2026-08-04
summary: Every term used anywhere in the product, alphabetical, each linking to its full entry.
keywords: glossary terms definitions vocabulary index alphabetical
---

One line each. Follow the link for the full entry.

| Term | One line |
|---|---|
| [Active state](#concept.active-vs-history) | What a field holds now, as opposed to what it used to hold. |
| [Alias](#concept.canonical-path) | An alternative name that resolves onto a canonical path. |
| [Audit entry](#concept.audit-entry) | One row recording a disclosure: handle, field keys, provider, model. |
| [Base unit](#concept.normalization) | The single unit a measure is converted to before storage. |
| [Canonical path](#concept.canonical-path) | The one dotted address a concept resolves to. |
| [Conflict](#concept.conflict) | A record that two values were asserted for one field. |
| [Count](#valuetype.count) | A plain number of countable things, with no unit of measure. |
| [Date](#valuetype.date) | A point in time. |
| [Decline](#concept.decline) | A value StateJar refused to store, kept with its reason. |
| [Disclosure](#concept.audit-entry) | State leaving StateJar for a model. |
| [Duration](#valuetype.duration) | A length of time, as opposed to a point in time. |
| [Dynamic field](#concept.dynamic-field) | A field for a concept the registry has no entry for. |
| [Extraction tier](#concept.extraction-tier) | One of the three extractors: rules, GLiNER2, LLM. |
| [Field](#concept.field) | One named slot holding one value. |
| [GLiNER2](#tier.gliner2) | Tier 2: schema-guided neural extraction. |
| [Handle](#concept.handle) | A content address for one exact state, written `shm_…`. |
| [History](#concept.active-vs-history) | Every value a field previously held. |
| [Identifier](#valuetype.identifier) | A code that names something rather than measuring it. |
| [Ingest](#api.memory.ingest) | The write path: extract, canonicalize, hash, store. |
| [`low_confidence`](#decline.low_confidence) | Declined: the proposing tier was not sure enough. |
| [Minimal disclosure](#ui.tab_retrieved_context) | Sending only the fields a question needs. |
| [Money](#valuetype.money) | An amount with a currency. Requires a positive currency signal. |
| [Namespace](#concept.scope) | Your account. Resolved from your credential, never passed in. |
| [Normalization](#concept.normalization) | Converting a value to one canonical form before storing it. |
| [`not an assertion`](#decline.not_an_assertion) | Declined: the clause was a question or a negation. |
| [`not provided`](#decline.not_provided) | Unresolved: a field was named with no value given. |
| [Ollama](#provider.ollama) | Locally-run models. Prompts never leave your computer. |
| [`pending`](#decline.pending) | Unresolved: a decision is explicitly outstanding. |
| [Percent](#valuetype.percent) | A proportion out of a hundred. |
| [Pipeline](#ui.pipeline_tracker) | The seven stages a message passes through. |
| [Provider](#gs.provider-setup) | The vendor whose model answers: OpenRouter, OpenAI, Anthropic, Google, Ollama. |
| [Proxy pattern](#api.patterns.proxy) | StateJar makes the model call for you. |
| [Quantity](#valuetype.quantity) | A number with a unit of measure. |
| [Qualifier](#concept.qualifier) | The part of a concept saying which end, side or bound. |
| [Ratio](#valuetype.ratio) | A relationship between two numbers. |
| [`rejected_value`](#decline.rejected_value) | Declined: the field exists, the value is the wrong kind. |
| [Reinforcement](#concept.reinforcement) | Restating a stored value. Nothing changes, including the handle. |
| [Replay](#api.audit.replay) | Reconstructing exactly what one audited call disclosed. |
| [Restore](#ui.restore_handle) | Adopting a sealed state into a session, verifying it on the way in. |
| [Retraction](#concept.retraction) | Taking a value back, leaving the field genuinely empty. |
| [Retrieval](#api.memory.query) | Selecting the minimal subset relevant to a question. |
| [Rules](#tier.rules) | Tier 1: deterministic patterns. Free, exact, reproducible. |
| [Scope](#concept.scope) | Which slice of memory an operation addresses. |
| [Session](#concept.session) | A named conversation thread. |
| [Sidecar pattern](#api.patterns.sidecar) | You keep your model call; StateJar supplies the subset. |
| [State](#concept.state) | The structured memory for a session at one point in time. |
| [State version](#api.memory.versions) | One link in a session's append-only chain of states. |
| [Supersession](#concept.supersession) | A new value replacing an old one, which moves to history. |
| [Text](#valuetype.text) | A value that is words rather than a measurement. |
| [Tier chip](#ui.tier_chips) | The badge showing which extractor produced how many fields. |
| [Token savings](#concept.token-savings) | How much smaller a disclosure was — against a stated baseline. |
| [`_unmapped`](#concept.decline) | Where declined values are parked, each with a reason. |
| [`unknown_key`](#decline.unknown_key) | Declined: nothing in the registry claims that name. |
| [Unknown type](#valuetype.unknown) | The classifier could not tell. Fails closed. |
| [Unresolved](#decline.not_provided) | A field named without a value. Nothing was rejected. |
| [`user rejected`](#decline.user_rejected) | A conflict record: one option refused in favour of another. |
| [`user unsure`](#decline.user_unsure) | Unresolved: uncertainty was signalled, so nothing was settled. |
| [Value type](#concept.value-type) | What kind of thing a value is. The core of the type guard. |
