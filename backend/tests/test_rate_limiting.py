"""
Rate limiting test — genuinely separate from every other test file,
since conftest.py's `app` fixture disables the real limiter globally
so it doesn't make unrelated tests flaky (see that fixture's own
docstring). This file deliberately re-enables it for one narrow test,
then restores the disabled state afterward, to prove the real
protection in rate_limiter.py actually works rather than just trusting
it because it's never been exercised.
"""
import pytest


@pytest.mark.asyncio
async def test_login_is_rate_limited_after_repeated_attempts(client, app):
    app.state.limiter.enabled = True
    try:
        responses = []
        for _ in range(10):
            resp = await client.post("/api/auth/login", json={
                "email": "nonexistent@example.com", "password": "wrong",
            })
            responses.append(resp.status_code)
        assert 429 in responses, f"Expected a 429 among repeated login attempts, got: {responses}"
    finally:
        app.state.limiter.enabled = False
