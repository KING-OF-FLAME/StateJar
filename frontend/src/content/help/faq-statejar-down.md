---
id: faq.statejar-down
title: What happens if StateJar is down?
category: faq
updated_at: 2026-08-04
summary: What happens if StateJar is down?
keywords: downtime outage availability offline reliability
---

Your model calls stop working if you use the [proxy
pattern](#api.patterns.proxy), because the call goes through us. With the
[sidecar pattern](#api.patterns.sidecar) your model call is your own — you lose
memory retrieval, not the conversation.

**Your state is not lost.** It is rows in a database, and every version is
addressable by its [handle](#concept.handle). Nothing about the format depends
on us being reachable: a handle is a hash of content, so state exported today
still verifies later.

This is a reason to prefer the sidecar for anything that must keep working.
