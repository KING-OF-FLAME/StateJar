---
id: ui.playground
title: Playground
category: interface
updated_at: 2026-08-04
summary: The working screen: chat on the left, the memory inspector on the right.
keywords: playground chat main screen workspace
---

The Playground is a full StateJar client. Everything it does is available
through the API.

Left column: the toolbar ([sessions](#ui.session_selector),
[model picker](#ui.model_selector), [restore](#ui.restore_handle), demo
buttons), the transcript, and the [message box](#ui.message_box).

Above both columns: the [seven-stage pipeline tracker](#ui.pipeline_tracker).

Right column: four tabs — [Memory State](#ui.tab_memory_state),
[Retrieved Context](#ui.tab_retrieved_context), [Handles](#ui.tab_handles),
[Audit](#ui.tab_audit) — with the [tier chips](#ui.tier_chips) and the
[handle line](#ui.handle_display) above them.

**Your transcript is stored in this browser, not on the server.** Switch
sessions and come back and it is exactly as you left it; open the same account
on another device and the memory is all there but the conversation is not. See
[the FAQ](#faq.transcript-storage).
