---
id: api.profile
title: Profile
category: api
updated_at: 2026-08-04
summary: Read and update the signed-in account's profile. Four optional fields, scoped to the caller.
keywords: profile account display name organization role use case settings
---

`GET · PATCH /api/v1/profile`

Four optional fields describing who the account belongs to: `display_name`,
`organization`, `role`, `use_case`.

**Scoped to the caller, with nothing to enumerate.** No id is accepted from the
client on either verb — the row is selected by the user id on the verified
credential, so there is no path to anyone else's profile and no id to probe.
Sending `user_id` in the body does nothing.

**An unset profile reads as empty, not 404.** Never having filled one in is a
normal state. The response carries `exists: false` so a client can tell "never
filled in" from "filled in and then cleared".

**PATCH is partial.** An absent key is left alone; an explicit `null` or a blank
string clears that field. That distinction is why it is a PATCH and not a PUT.

**Rejected, never coerced.** A value that fails validation comes back `422` with
a per-field reason, and nothing is written:

```json
{
  "detail": {
    "error": "profile rejected",
    "fields": { "display_name": "must be 80 characters or fewer (got 210)" }
  }
}
```

One bad field rejects the whole request, so a partial write can never leave you
wondering which half of an edit survived. This is the same fail-closed principle
the extractor applies to a value — see [decline](#concept.decline). The only
liberty taken is trimming surrounding whitespace, because a trailing space is a
typing artefact rather than something you meant.

**Deliberately small.** No avatar bytes, no uploads, nothing sensitive, and every
field is capped and single-line. A profile that cannot hold a file cannot leak
one, and the length caps also keep the profile from becoming a back door for the
one thing StateJar refuses to store — see
[where chat history is stored](#faq.transcript-storage).
