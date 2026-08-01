"""Transport hardening: rate limits and security response headers.

Rate limits protect the two endpoints where guessing pays off (login,
signup) and the one that spends money on the user's behalf (/chat).

Storage is in-process, which is the honest fit for a single Railway
instance: it resets on redeploy and is not shared between replicas. If
StateJar is ever scaled out, point the limiter at Redis via
`Limiter(storage_uri=...)` — the limits themselves need not change.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import jwt as pyjwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.security import decode_token

# --- limit definitions --------------------------------------------------------

LOGIN_LIMIT = "5/minute"      # credential stuffing
SIGNUP_LIMIT = "10/hour"      # bulk account creation
CHAT_LIMIT = "60/hour"        # provider-key abuse / cost exhaustion


def user_or_ip(request: Request) -> str:
    """Rate-limit key for authenticated endpoints.

    Keyed on the JWT subject so one abusive account cannot burn the quota of
    everyone else behind the same NAT, and so rotating IPs does not reset a
    user's budget. Falls back to the client address when there is no usable
    token — an unauthenticated request is rejected by the route anyway.
    """
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return f"user:{decode_token(token)['sub']}"
        except (pyjwt.PyJWTError, KeyError):
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=get_remote_address)


# --- security headers ---------------------------------------------------------

# Applied to every response, including errors.
#   HSTS               force TLS on repeat visits (ignored over plain HTTP)
#   nosniff            stop MIME-type guessing turning JSON into script
#   DENY               the API is never framed; kills clickjacking outright
#   no-referrer        never leak an authenticated URL to a third-party host
SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach the headers above without overriding anything already set."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        return response
