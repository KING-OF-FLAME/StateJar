---
id: concept.value-type
title: Value type
category: concepts
updated_at: 2026-08-04
summary: What kind of thing a value is: money, quantity, date, duration, percent, ratio, identifier, count, text.
keywords: type classification money quantity date validation
---

**Definition.** The classification a value gets before it is stored: [money](#valuetype.money), [quantity](#valuetype.quantity), [date](#valuetype.date), [duration](#valuetype.duration), [percent](#valuetype.percent), [ratio](#valuetype.ratio), [identifier](#valuetype.identifier), [count](#valuetype.count), [text](#valuetype.text), or unknown.

**Why it exists.** This is the whole trick. StateJar hardcodes what a *value* can be, not what a *field* can be called — which is why it works in domains it has never seen.

**Where you see it.** Implicitly, in how a value renders. A money value shows a currency; a quantity shows a unit.

**Worked example.** `24 tonnes` classifies as a quantity. A money field will not accept it, so it is not stored as twenty-four rupees. That single check is the difference between a correct memory and a confidently wrong one.

**Common misunderstanding.** That the type comes from the field. It comes from the value and its surrounding clause. The field only says which types it will accept.
