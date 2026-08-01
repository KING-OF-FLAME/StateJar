# Security

StateJar stores two things people care about: the structured memory extracted
from their conversations, and the provider API keys they bring with them. This
document records what each is protected against, how that protection is
enforced in code, and what is deliberately out of scope.

Every mitigation below has a test in `backend/tests/test_security.py`. Several
of those are *static* — they parse `backend/app/` and fail if a whole class of
bug reappears, rather than only checking that today's code is safe.

## Threat model

| # | Threat | Mitigation | Enforced by |
|---|--------|-----------|-------------|
| 1 | **SQL injection** via login, signup, or any query field | No SQL is ever built by string interpolation. All access goes through SQLAlchemy Core expressions, which bind parameters; the only `text()` calls are static DDL in the startup migration | `test_sqli_on_login_is_refused`, `test_sqli_does_not_execute`, `test_no_dynamically_built_sql_in_app_code` (AST scan, rejects f-strings, `.format()`, `%`) |
| 2 | **Credential stuffing** against `/auth/login` | 5 requests/minute per IP. Failed attempts count, so a wrong-password loop is throttled at the same rate as a correct one | `test_sixth_rapid_login_is_rate_limited` |
| 3 | **Bulk account creation** | 10 signups/hour per IP | `test_eleventh_signup_is_rate_limited` |
| 4 | **Provider-credit exhaustion** on `/chat` | 60 requests/hour, keyed on the **JWT subject, not the IP** — one abusive account cannot spend everyone else's quota, and rotating IPs does not reset a user's budget | `test_chat_limit_is_keyed_per_user`, `test_the_three_limits_are_actually_registered` |
| 5 | **Password disclosure** if the database leaks | Passwords are stored only as bcrypt hashes (per-password salt, work factor 12). Plaintext is never persisted or returned | `test_signup_creates_user` (no hash in response) |
| 6 | **Provider-key disclosure** if the database leaks | Keys are encrypted at rest with AES-256-GCM under a key derived from `AES_KEY`. GCM's auth tag makes tampering detectable | `test_encrypt_decrypt_roundtrip`, `test_tampered_ciphertext_rejected` |
| 7 | **Provider-key disclosure via the API** | A saved key is never returned again. Both the save response and the listing expose only `key_last4` | `test_saving_a_key_never_echoes_it`, `test_keys_listing_has_no_full_key` |
| 8 | **Provider-key disclosure via logs** | No secret is passed to a logger anywhere in `app/`. Enforced statically, because log records leave the process for stdout and any aggregator | `test_no_secret_is_ever_handed_to_the_logger` (AST scan) |
| 9 | **Reading another user's keys or memory** | Every query filters on the authenticated `user_id`; handles are not capability tokens, so knowing one grants nothing | `test_another_user_cannot_see_your_keys`, `test_state_by_handle_scoped_to_user` |
| 10 | **Forged JWT** — attacker-chosen signing key | `decode` pins HS256 and verifies against `JWT_SECRET` | `test_token_signed_with_another_secret_is_rejected` |
| 11 | **Forged JWT** — `alg: none` confusion | Same pinning: an unsigned token is refused | `test_unsigned_token_is_rejected` |
| 12 | **Replay of a stolen token, indefinitely** | Tokens carry `iat`/`exp` with a 24h TTL, verified on every request | `test_expired_token_is_rejected`, `test_tokens_carry_a_bounded_lifetime` |
| 13 | **Cross-origin theft from a hostile page** | CORS is an exact allowlist (localhost dev, the Vercel preview, apex and `www` production). No wildcard, no regex | `test_cors_allowlist_is_exact`, `test_unknown_origin_is_not_allowed` |
| 14 | **Clickjacking** — the API framed by an attacker page | `X-Frame-Options: DENY` on every response | `test_security_headers_on_every_response` |
| 15 | **MIME sniffing** turning a JSON response into executable script | `X-Content-Type-Options: nosniff` | same |
| 16 | **Referrer leakage** of an authenticated URL to a third party | `Referrer-Policy: no-referrer` | same |
| 17 | **Downgrade / SSL-strip on repeat visits** | `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` | same |
| 18 | **Headers stripped on error paths** | The middleware wraps every response, including 401s and 429s, not just successes | `test_rate_limited_response_still_carries_security_headers` |

## Notes and limitations

**Rate-limit storage is in-process.** Counters live in the app's memory, so
they reset on redeploy and are not shared between replicas. That is the honest
fit for a single Railway instance. To scale out, give the limiter a Redis URI
(`Limiter(storage_uri=...)` in `backend/app/security.py`) — the limits
themselves do not change.

**IP limits are shared behind NAT.** Everyone on one office or venue network
counts as a single client. For an event where many people sign up over the
same WiFi, set `RATE_LIMIT_ENABLED=false` for the duration rather than locking
the room out.

**Handles are not secrets, and not capabilities.** A handle is a SHA-256
digest of canonical state content. Two users with byte-identical states get
the same handle by design — that is the deduplication property. Access is
authorised by `user_id` on every read, never by possession of a handle.

**Provider keys are decrypted in memory to make a call.** Encryption at rest
protects a database leak, not a compromised application host. Anyone with code
execution on the API process can read `AES_KEY` and the decrypted key.

**No account lockout, and no MFA.** Rate limiting slows credential stuffing
but does not stop a patient attacker with many IPs. Both are deliberate scope
decisions for a final-year project, not oversights.

**Optional ML layers are not a security boundary.** GLiNER extraction and
semantic retrieval download model weights from Hugging Face on first use.
They are off in production (the packages are not installed there) and should
only be enabled where that download is acceptable.

## Reporting

This is an academic project (Indian Patent App. No. 202621017626, Team Hello
World). Please open a GitHub issue for anything you find; there is no bounty
and no embargo process.
