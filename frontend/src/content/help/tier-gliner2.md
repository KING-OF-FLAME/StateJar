---
id: tier.gliner2
title: Tier 2: GLiNER2
category: reference
updated_at: 2026-08-04
summary: Schema-guided neural extraction for what the patterns missed.
keywords: gliner tier2 neural ner spans model
---

**What it is.** A small neural span-labelling model (`urchade/gliner_multi-v2.1`)
given a schema of labels to look for.

**What it catches.** Values stated in a shape the patterns do not cover —
a name in an unusual position, a city inside a longer phrase.

**Confidence.** 0.55, with a floor of 0.5 on the model's own score. Lower than
rules, deliberately: a span guess is not a pattern match, and fields that
demand more confidence will decline it with
[`low_confidence`](#decline.low_confidence).

**Dependencies.** `gliner` and `torch`, which live in `requirements-ml.txt`
rather than `requirements.txt` — production installs stay small and do not pull
a CPU torch wheel. Where those are absent this tier simply does not run.

**Controlled by** [`EXTRACTOR_MODE`](#settings.extractor_mode).

Whatever it proposes goes through the same type guard and the same registry as
everything else. A neural span is not more entitled to a field than a regex was.
