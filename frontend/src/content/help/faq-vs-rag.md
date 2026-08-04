---
id: faq.vs-rag
title: How is this different from RAG?
category: faq
updated_at: 2026-08-04
summary: How is this different from RAG?
keywords: rag retrieval augmented generation embeddings vector difference compare
---

They solve different problems and compose fine.

**RAG retrieves documents.** You have a corpus, you embed it, and at query time
you fetch passages that look similar to the question. It is excellent at "what
does the manual say about X".

**StateJar tracks state.** There is no corpus. There are fields with current
values, and the question is not "what is similar" but "what is true now".

The concrete difference is contradiction. If a document says the budget is 5000
and a later one says 8000, a similarity search may return both and the model
picks. In StateJar the field holds 8000 and 5000 is in history, so both cannot
be returned. See [active state vs history](#concept.active-vs-history).

The other difference is that similarity has no notion of type. This is the
failure StateJar exists to prevent — see
[value type](#concept.value-type).

**Use both** when you have documents *and* facts that change.
