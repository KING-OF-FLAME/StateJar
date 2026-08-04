---
id: ui.help
title: This help centre
category: interface
updated_at: 2026-08-04
summary: Search, categories, deep links, and a coverage test that keeps it current.
keywords: help documentation search index guide manual
---

Every entry has a stable id and its own anchor, so any entry can be linked
directly — `#concept.handle` jumps to the handle entry.

**Search** matches titles, summaries, keywords and bodies. Try "declined", "why
wasn't this stored", or "ollama".

**Last updated** on each entry comes from the file itself, not from a hardcoded
string, so it cannot claim to be fresher than it is.

Coverage is enforced by a test. Every API endpoint, setting, provider, tier,
[decline reason](#concept.decline), value type and UI surface in the shipped
product must have an entry here, or the build fails naming exactly what is
undocumented. Deliberate exclusions are listed in the test with a written
reason.
