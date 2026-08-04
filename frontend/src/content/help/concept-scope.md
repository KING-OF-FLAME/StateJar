---
id: concept.scope
title: Scope: session, user, namespace
category: concepts
updated_at: 2026-08-04
summary: Which slice of memory a read or write applies to.
keywords: scope session user namespace multi-tenant isolation
---

**Definition.** Which slice of memory an operation addresses. **Session** is one thread. **User** is one end user across their sessions. **Namespace** is your whole StateJar account.

**Why it exists.** An application has many end users, and each of them has many conversations. Without a scope, either everyone shares one memory or nobody keeps one across sessions.

**Where you see it.** Today: session scope is what the Playground uses, and the account is the namespace. Cross-session recall works by moving a handle.

**Worked example.** In the Playground, each session dropdown entry is one session scope, and everything you have is one namespace.

**Common misunderstanding.** That namespace is something you pass in. It is never accepted from a client — it is resolved from your credential, so one account can never address another's memory.
