"""
Shared pytest fixtures for the PropWise AI backend test suite.

HONESTY NOTE ON TEST DATABASE: these tests run against mongomock-motor,
an in-memory, real, widely-used fake of MongoDB's async (Motor) API -
not a full behavioral clone of real MongoDB. It does not perfectly
replicate every aggregation pipeline operator or edge case. These
tests give real, meaningful protection against logic regressions
(especially the multi-tenancy org-scoping this app depends on) but are
not a substitute for also testing against a real MongoDB instance
before shipping a major release - a genuine, stated gap, not something
this suite claims to fully close.

Every collection in db.py is bound as a module-level name
(`xxx_col = db["xxx"]`), and every router does `from db import
xxx_col` at import time. That means the mock database MUST be patched
into place before main.py (and therefore every router) is ever
imported, or their collection references would bind to the real
(and, in CI, unreachable) MongoDB client instead. See
patch_db_with_mock below for exactly how that's done.
"""
import os

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_rentflow")
os.environ.setdefault("JWT_SECRET", "test-only-secret-key-not-for-real-use-32bytes")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")
os.environ.setdefault("SEED_SECRET", "test-seed-secret")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


@pytest.fixture(scope="session", autouse=True)
def patch_db_with_mock():
    """Patches every *_col name in db.py to point at an in-memory
    mongomock-motor database, before any router module is imported.
    autouse + session-scoped: this must run exactly once, before the
    `app` fixture below ever imports main.py."""
    import db as db_module
    from mongomock_motor import AsyncMongoMockClient

    mock_client = AsyncMongoMockClient()
    mock_db = mock_client[os.environ["DB_NAME"]]
    db_module.client = mock_client
    db_module.db = mock_db
    for name in dir(db_module):
        if name.endswith("_col"):
            setattr(db_module, name, mock_db[name[:-4]])
    return mock_db


@pytest.fixture(scope="session")
def app(patch_db_with_mock):
    """Imports main.py (and therefore every router) only after the
    database has already been patched above."""
    import main

    # Real rate limiting (rate_limiter.py) is genuinely wired into
    # this app and IS exercised directly by test_rate_limiting.py -
    # but leaving it enabled here would make every OTHER test in this
    # suite flaky depending on how many requests happened to run
    # before it in the same session (slowapi's own default in-memory
    # store has no per-test reset hook). Disabled globally for this
    # fixture; test_rate_limiting.py re-enables it for its own
    # narrow, dedicated test and restores it afterward.
    main.limiter.enabled = False
    return main.app


@pytest_asyncio.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def clean_db(patch_db_with_mock):
    """Drops every collection's documents after each test - real
    isolation between tests, not just hoping different tests' data
    doesn't collide. Runs after (not before) each test so a failed
    test's real data is still inspectable if you drop into a debugger
    mid-test."""
    yield
    for name in await patch_db_with_mock.list_collection_names():
        await patch_db_with_mock[name].delete_many({})


async def _signup(client: AsyncClient, org_name: str, email: str) -> dict:
    """Real signup through the actual endpoint - not a database
    shortcut - so these tests exercise the real signup code path
    (including the real 14-day trial + isOrgOwner assignment) rather
    than assuming it behaves a particular way."""
    resp = await client.post("/api/auth/signup-organization", json={
        "organizationName": org_name,
        "name": f"Owner of {org_name}",
        "email": email,
        "password": "testpass123",
    })
    assert resp.status_code == 200, f"signup failed: {resp.status_code} {resp.text}"
    data = resp.json()
    return {
        "token": data["accessToken"],
        "orgId": data["user"]["orgId"],
        "userId": data["user"]["id"],
        "email": email,
    }


@pytest_asyncio.fixture
async def org_a(client):
    """A real, fully signed-up organization - 'Org A' throughout the
    multi-tenancy test suite."""
    return await _signup(client, "Org A", "ownera@example.com")


@pytest_asyncio.fixture
async def org_b(client):
    """A second, genuinely separate organization - 'Org B' throughout
    the multi-tenancy test suite. The entire point of these fixtures
    existing side by side is to assert Org A can never see or modify
    Org B's data, and vice versa."""
    return await _signup(client, "Org B", "ownerb@example.com")


def auth_headers(org: dict) -> dict:
    return {"Authorization": f"Bearer {org['token']}"}
