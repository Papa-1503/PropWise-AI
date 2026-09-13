"""
Two-factor authentication tests — the login flow is the single
highest-stakes area to get wrong in this whole app, so this file goes
beyond the happy path to verify the real security properties directly:
a pending-2FA token can never be used as a real access token, a used
backup code can never be reused, and a wrong code is always rejected.
"""
import pyotp
import pytest

from tests.conftest import auth_headers

TEST_PASSWORD = "testpass123"  # matches conftest.py's _signup fixture


async def _setup_and_enable_2fa(client, org):
    """Real, shared setup: calls the actual /setup and /enable
    endpoints (not a shortcut that writes totpSecret directly to the
    database), so every test using this fixture exercises the real
    confirm-before-enable flow at least once."""
    setup_resp = await client.post("/api/auth/2fa/setup", headers=auth_headers(org))
    assert setup_resp.status_code == 200, setup_resp.text
    secret = setup_resp.json()["secret"]

    totp = pyotp.TOTP(secret)
    code = totp.now()
    enable_resp = await client.post("/api/auth/2fa/enable", json={"code": code}, headers=auth_headers(org))
    assert enable_resp.status_code == 200, enable_resp.text
    backup_codes = enable_resp.json()["backupCodes"]
    return secret, backup_codes


@pytest.mark.asyncio
async def test_setup_returns_secret_and_qr_code_without_enabling(client, org_a):
    resp = await client.post("/api/auth/2fa/setup", headers=auth_headers(org_a))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["secret"]
    assert data["qrCodeDataUri"].startswith("data:image/png;base64,")

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(org_a))
    assert status_resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_enable_rejects_wrong_code(client, org_a):
    setup_resp = await client.post("/api/auth/2fa/setup", headers=auth_headers(org_a))
    resp = await client.post("/api/auth/2fa/enable", json={"code": "000000"}, headers=auth_headers(org_a))
    assert resp.status_code == 400

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(org_a))
    assert status_resp.json()["enabled"] is False


@pytest.mark.asyncio
async def test_enable_with_correct_code_activates_and_returns_8_backup_codes(client, org_a):
    secret, backup_codes = await _setup_and_enable_2fa(client, org_a)
    assert len(backup_codes) == 8
    assert len(set(backup_codes)) == 8  # all genuinely unique

    status_resp = await client.get("/api/auth/2fa/status", headers=auth_headers(org_a))
    assert status_resp.json()["enabled"] is True


@pytest.mark.asyncio
async def test_login_with_2fa_enabled_requires_second_step(client, org_a):
    await _setup_and_enable_2fa(client, org_a)

    resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("requires2FA") is True
    assert "pendingToken" in data
    assert "accessToken" not in data  # the real, critical property: no real token issued yet


@pytest.mark.asyncio
async def test_login_2fa_completes_with_correct_totp_code(client, org_a):
    secret, _ = await _setup_and_enable_2fa(client, org_a)

    login_resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    pending_token = login_resp.json()["pendingToken"]

    code = pyotp.TOTP(secret).now()
    resp = await client.post("/api/auth/login/2fa", json={"pendingToken": pending_token, "code": code})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["accessToken"]
    assert data["user"]["email"] == org_a["email"]


@pytest.mark.asyncio
async def test_login_2fa_rejects_wrong_code(client, org_a):
    await _setup_and_enable_2fa(client, org_a)
    login_resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    pending_token = login_resp.json()["pendingToken"]

    resp = await client.post("/api/auth/login/2fa", json={"pendingToken": pending_token, "code": "000000"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pending_2fa_token_cannot_be_used_as_a_real_access_token(client, org_a):
    """The single most important security property of this whole
    feature: a token issued after password-only verification (before
    the real 2FA code is checked) must be completely unusable as a
    substitute for a real access token - otherwise 2FA would be
    trivially bypassable."""
    await _setup_and_enable_2fa(client, org_a)
    login_resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    pending_token = login_resp.json()["pendingToken"]

    resp = await client.get("/api/auth/2fa/status", headers={"Authorization": f"Bearer {pending_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_backup_code_works_and_is_single_use(client, org_a):
    _, backup_codes = await _setup_and_enable_2fa(client, org_a)
    a_backup_code = backup_codes[0]

    login_resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    pending_token = login_resp.json()["pendingToken"]

    resp = await client.post("/api/auth/login/2fa", json={"pendingToken": pending_token, "code": a_backup_code})
    assert resp.status_code == 200, resp.text

    # The SAME backup code must never work a second time, even against a fresh pending token.
    login_resp2 = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    pending_token2 = login_resp2.json()["pendingToken"]
    resp2 = await client.post("/api/auth/login/2fa", json={"pendingToken": pending_token2, "code": a_backup_code})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_disable_requires_correct_password(client, org_a):
    await _setup_and_enable_2fa(client, org_a)

    wrong_resp = await client.post("/api/auth/2fa/disable", json={"password": "wrong-password"}, headers=auth_headers(org_a))
    assert wrong_resp.status_code == 401
    still_enabled = await client.get("/api/auth/2fa/status", headers=auth_headers(org_a))
    assert still_enabled.json()["enabled"] is True

    correct_resp = await client.post("/api/auth/2fa/disable", json={"password": TEST_PASSWORD}, headers=auth_headers(org_a))
    assert correct_resp.status_code == 200, correct_resp.text

    now_disabled = await client.get("/api/auth/2fa/status", headers=auth_headers(org_a))
    assert now_disabled.json()["enabled"] is False

    # And login should be single-step again, exactly like before 2FA was ever enabled.
    login_resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    assert "accessToken" in login_resp.json()


@pytest.mark.asyncio
async def test_login_without_2fa_enabled_is_unaffected(client, org_a):
    """Real, direct backward-compatibility check: an account that has
    never touched 2FA gets the exact same single-step login it always
    has."""
    resp = await client.post("/api/auth/login", json={"email": org_a["email"], "password": TEST_PASSWORD})
    assert resp.status_code == 200
    data = resp.json()
    assert "accessToken" in data
    assert "requires2FA" not in data
