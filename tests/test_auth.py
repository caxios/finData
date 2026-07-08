"""
Tests for the findata authentication system.

Covers:
- Accounts DB CRUD (users, API keys, hashing)
- FastAPI auth dependency (401/200 behavior)
- Key deactivation
- last_used_at tracking
- Plaintext key never stored in DB
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# Unit tests for accounts_db (no FastAPI needed)
# =====================================================================

class TestAccountsDB:
    """Test the accounts database CRUD operations directly."""

    @pytest.fixture(autouse=True)
    def _setup_db(self, tmp_path):
        """Create a fresh accounts DB for each test."""
        self.db_path = str(tmp_path / "test_accounts.db")

    def test_create_user(self):
        from findata.server.db.accounts_db import create_user, ensure_accounts_schema
        ensure_accounts_schema(self.db_path)
        uid = create_user("test@example.com", plan="free", db_path=self.db_path)
        assert isinstance(uid, int)
        assert uid > 0

    def test_create_user_idempotent(self):
        from findata.server.db.accounts_db import create_user, ensure_accounts_schema
        ensure_accounts_schema(self.db_path)
        uid1 = create_user("same@example.com", plan="free", db_path=self.db_path)
        uid2 = create_user("same@example.com", plan="free", db_path=self.db_path)
        assert uid1 == uid2

    def test_create_api_key_format(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("key@example.com", db_path=self.db_path)
        key = create_api_key(uid, label="test", db_path=self.db_path)
        assert key.startswith("fd_live_")
        assert len(key) == len("fd_live_") + 32  # prefix + 32 base62 chars

    def test_create_api_key_test_env(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("env@example.com", db_path=self.db_path)
        key = create_api_key(uid, env="test", db_path=self.db_path)
        assert key.startswith("fd_test_")

    def test_plaintext_key_not_in_db(self):
        """The raw key must NOT be stored in the database — only its hash."""
        from findata.server.db.accounts_db import (
            create_user, create_api_key, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("hash@example.com", db_path=self.db_path)
        plaintext = create_api_key(uid, db_path=self.db_path)

        from findata.server.db.engine import connect
        # Inspect the same DB the key was written to (db_path is required for
        # the SQLite backend; ignored under Postgres).
        conn = connect(self.db_path)
        rows = conn.execute("SELECT key_prefix, key_hash FROM api_keys").fetchall()
        conn.close()

        for prefix, key_hash in rows:
            assert plaintext != prefix, "Plaintext leaked into key_prefix"
            assert plaintext != key_hash, "Plaintext stored as key_hash"
            assert plaintext not in (prefix or ""), "Plaintext substring in prefix"
            assert plaintext not in (key_hash or ""), "Plaintext substring in hash"

    def test_get_user_by_valid_key(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, get_user_by_key, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("valid@example.com", plan="pro", db_path=self.db_path)
        key = create_api_key(uid, label="lookup test", db_path=self.db_path)

        user = get_user_by_key(key, db_path=self.db_path)
        assert user is not None
        assert user["email"] == "valid@example.com"
        assert user["plan"] == "pro"
        assert user["key_label"] == "lookup test"
        assert user["active"] == 1

    def test_get_user_by_invalid_key(self):
        from findata.server.db.accounts_db import (
            get_user_by_key, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        user = get_user_by_key("fd_live_totallyinvalidkey1234567890", db_path=self.db_path)
        assert user is None

    def test_deactivate_key_blocks_lookup(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, get_user_by_key,
            deactivate_key, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("deact@example.com", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        # Key works initially
        assert get_user_by_key(key, db_path=self.db_path) is not None

        # Get key_id, deactivate
        user = get_user_by_key(key, db_path=self.db_path)
        deactivate_key(user["key_id"], db_path=self.db_path)

        # Now lookup returns None
        assert get_user_by_key(key, db_path=self.db_path) is None

    def test_update_last_used(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, get_user_by_key,
            update_last_used, ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("used@example.com", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        user = get_user_by_key(key, db_path=self.db_path)
        assert user["last_used_at"] is None

        update_last_used(user["key_id"], db_path=self.db_path)

        user = get_user_by_key(key, db_path=self.db_path)
        assert user["last_used_at"] is not None

    def test_list_keys_for_user(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, list_keys_for_user,
            ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("list@example.com", db_path=self.db_path)
        create_api_key(uid, label="key1", db_path=self.db_path)
        create_api_key(uid, label="key2", db_path=self.db_path)

        keys = list_keys_for_user(uid, db_path=self.db_path)
        assert len(keys) == 2
        labels = {k["label"] for k in keys}
        assert labels == {"key1", "key2"}

    def test_owner_plan(self):
        from findata.server.db.accounts_db import (
            create_user, create_api_key, get_user_by_key,
            ensure_accounts_schema,
        )
        ensure_accounts_schema(self.db_path)
        uid = create_user("owner@example.com", plan="owner", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        user = get_user_by_key(key, db_path=self.db_path)
        assert user is not None
        assert user["plan"] == "owner"


# =====================================================================
# Integration tests for FastAPI auth (via TestClient)
# =====================================================================

class TestFastAPIAuth:
    """Test the auth dependency via FastAPI's TestClient."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Patch the DB path and create a test app with auth."""
        self.db_path = str(tmp_path / "test_accounts.db")
        # Patch the canonical ACCOUNTS_DB in config (the single source of truth)
        monkeypatch.setattr(
            "findata.server.db.config.ACCOUNTS_DB", self.db_path
        )
        # Patch FINDATA_DATA_DIR so startup doesn't touch the real dir
        monkeypatch.setenv("FINDATA_DATA_DIR", str(tmp_path / "findata-data"))

    def _make_app(self):
        """Create a minimal FastAPI app with one authed route for testing."""
        from fastapi import Depends, FastAPI
        from findata.server.auth import require_api_key
        from findata.server.db.accounts_db import ensure_accounts_schema

        ensure_accounts_schema(self.db_path)

        test_app = FastAPI()

        @test_app.get("/health")
        def health():
            return {"status": "ok"}

        @test_app.get("/protected", dependencies=[Depends(require_api_key)])
        def protected():
            return {"data": "secret"}

        return test_app

    def test_health_no_auth(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._make_app())
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_protected_no_key_returns_401(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._make_app())
        resp = client.get("/protected")
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"]["error"]["code"] == "MISSING_API_KEY"

    def test_protected_invalid_key_returns_401(self):
        from fastapi.testclient import TestClient
        client = TestClient(self._make_app())
        resp = client.get(
            "/protected",
            headers={"X-API-Key": "fd_live_totallyinvalidkey1234567890"},
        )
        assert resp.status_code == 401
        body = resp.json()
        assert body["detail"]["error"]["code"] == "INVALID_API_KEY"

    def test_protected_valid_key_returns_200(self):
        from fastapi.testclient import TestClient
        from findata.server.db.accounts_db import create_user, create_api_key

        uid = create_user("api@test.com", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        client = TestClient(self._make_app())
        resp = client.get(
            "/protected",
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 200
        assert resp.json() == {"data": "secret"}

    def test_protected_bearer_header(self):
        from fastapi.testclient import TestClient
        from findata.server.db.accounts_db import create_user, create_api_key

        uid = create_user("bearer@test.com", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        client = TestClient(self._make_app())
        resp = client.get(
            "/protected",
            headers={"Authorization": f"Bearer {key}"},
        )
        assert resp.status_code == 200

    def test_protected_deactivated_key_returns_401(self):
        from fastapi.testclient import TestClient
        from findata.server.db.accounts_db import (
            create_user, create_api_key, get_user_by_key, deactivate_key,
        )

        uid = create_user("deact@test.com", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)
        user = get_user_by_key(key, db_path=self.db_path)
        deactivate_key(user["key_id"], db_path=self.db_path)

        client = TestClient(self._make_app())
        resp = client.get(
            "/protected",
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 401

    def test_owner_key_works(self):
        from fastapi.testclient import TestClient
        from findata.server.db.accounts_db import create_user, create_api_key

        uid = create_user("owner@test.com", plan="owner", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        client = TestClient(self._make_app())
        resp = client.get(
            "/protected",
            headers={"X-API-Key": key},
        )
        assert resp.status_code == 200

    def test_last_used_at_updates_on_request(self):
        from fastapi.testclient import TestClient
        from findata.server.db.accounts_db import (
            create_user, create_api_key, get_user_by_key,
        )

        uid = create_user("track@test.com", db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)

        # Before any request, last_used_at is None
        user = get_user_by_key(key, db_path=self.db_path)
        assert user["last_used_at"] is None

        # Make a request
        client = TestClient(self._make_app())
        client.get("/protected", headers={"X-API-Key": key})

        # Now last_used_at should be set
        user = get_user_by_key(key, db_path=self.db_path)
        assert user["last_used_at"] is not None
