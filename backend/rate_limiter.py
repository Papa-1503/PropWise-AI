"""
Shared rate limiter (slowapi) — genuinely missing before this: no
endpoint in this app had any request-rate protection at all, confirmed
by a direct search. The two real risk categories this addresses:

1. /api/auth/login and /api/auth/register are unauthenticated by
   design (a login page can't require you to already be logged in).
   Without rate limiting, either is open to unbounded password
   guessing — and register specifically accepts an inviteCode, which
   without a rate limit could be brute-forced to activate an account
   for a unit that isn't the attacker's.
2. /api/payments/{charge_id}/checkout and /setup-intent are
   authenticated, but each call triggers a real Stripe API request —
   unbounded calls are a real cost/abuse surface even from a
   legitimate logged-in account (a compromised session, a buggy
   frontend retry loop, etc.).

Limits are keyed by IP address (slowapi's standard, simplest pattern)
— generous enough that a real person mistyping a password or
double-clicking "Pay" a few times never hits the limit, tight enough
to meaningfully slow down automated abuse.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
