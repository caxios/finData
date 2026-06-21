"""
Tests for the metering, quota, and rate limiting system.

Covers:
- Credit cost resolution
- Usage DB recording and rollup
- Metering middleware (records usage after response)
- Quota enforcement (429 when exceeded)
- Rate limiting (429 with Retry-After)
- Owner exemption from both quota and rate limits
- /api/usage endpoint
"""

import time

import pytest

from findata.server.billing.costs import get_endpoint_credits
from findata.server.billing.plans import PlanConfig, get_plan


# =====================================================================
# Unit tests for billing/costs.py
# =====================================================================

class TestEndpointCosts:
    def test_exact_match_cache_read(self):
        assert get_endpoint_credits("/api/trades") == 1

    def test_exact_match_transcript(self):
        assert get_endpoint_credits("/api/transcript") == 10

    def test_exact_match_chat(self):
        assert get_endpoint_credits("/api/filings/chat") == 20

    def test_prefix_match_documents(self):
        assert get_endpoint_credits("/api/documents/AAPL/list") == 1

    def test_prefix_match_financials(self):
        assert get_endpoint_credits("/api/financials/AAPL/detail") == 1

    def test_prefix_match_company_data(self):
        assert get_endpoint_credits("/api/company-data/AAPL") == 3

    def test_unknown_endpoint_default(self):
        assert get_endpoint_credits("/api/unknown/endpoint") == 1

    def test_chat_more_expensive_than_cache_read(self):
        chat_cost = get_endpoint_credits("/api/filings/chat")
        cache_cost = get_endpoint_credits("/api/trades")
        assert chat_cost > cache_cost


# =====================================================================
# Unit tests for billing/plans.py
# =====================================================================

class TestPlans:
    def test_owner_unlimited(self):
        plan = get_plan("owner")
        assert plan.monthly_credits is None

    def test_free_has_quota(self):
        plan = get_plan("free")
        assert plan.monthly_credits is not None
        assert plan.monthly_credits > 0

    def test_pro_higher_than_free(self):
        free = get_plan("free")
        pro = get_plan("pro")
        assert pro.monthly_credits > free.monthly_credits

    def test_unknown_plan_falls_back_to_free(self):
        plan = get_plan("nonexistent")
        free = get_plan("free")
        assert plan == free


# =====================================================================
# Unit tests for usage_db
# =====================================================================

class TestUsageDB:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.db_path = str(tmp_path / "test_usage.db")

    def test_record_and_read(self):
        from findata.server.db.usage_db import (
            record_usage, get_month_credits, ensure_usage_schema,
        )
        ensure_usage_schema(self.db_path)
        record_usage(1, "/api/trades", 1, 200, db_path=self.db_path)
        record_usage(1, "/api/trades", 1, 200, db_path=self.db_path)
        record_usage(1, "/api/transcript", 10, 200, db_path=self.db_path)

        total = get_month_credits(1, db_path=self.db_path)
        assert total == 12  # 1 + 1 + 10

    def test_different_users_separate(self):
        from findata.server.db.usage_db import (
            record_usage, get_month_credits, ensure_usage_schema,
        )
        ensure_usage_schema(self.db_path)
        record_usage(1, "/api/trades", 5, 200, db_path=self.db_path)
        record_usage(2, "/api/trades", 3, 200, db_path=self.db_path)

        assert get_month_credits(1, db_path=self.db_path) == 5
        assert get_month_credits(2, db_path=self.db_path) == 3

    def test_zero_credits_for_new_user(self):
        from findata.server.db.usage_db import (
            get_month_credits, ensure_usage_schema,
        )
        ensure_usage_schema(self.db_path)
        assert get_month_credits(999, db_path=self.db_path) == 0

    def test_usage_summary(self):
        from findata.server.db.usage_db import (
            record_usage, get_usage_summary, ensure_usage_schema,
        )
        ensure_usage_schema(self.db_path)
        record_usage(1, "/api/trades", 1, 200, db_path=self.db_path)
        record_usage(1, "/api/transcript", 10, 200, db_path=self.db_path)

        summary = get_usage_summary(1, db_path=self.db_path)
        assert summary["credits_used"] == 11
        assert len(summary["endpoints"]) == 2


# =====================================================================
# Unit tests for rate limiter token bucket
# =====================================================================

class TestTokenBucket:
    def test_bucket_allows_burst(self):
        from findata.server.middleware.ratelimit import TokenBucket
        bucket = TokenBucket(rate=1.0, burst=5)
        for _ in range(5):
            assert bucket.consume() is None  # all succeed
        result = bucket.consume()
        assert result is not None  # 6th should fail
        assert result > 0

    def test_bucket_refills(self):
        from findata.server.middleware.ratelimit import TokenBucket
        bucket = TokenBucket(rate=10.0, burst=5)
        # Exhaust all tokens
        for _ in range(5):
            bucket.consume()
        # Simulate time passing
        bucket.last_refill -= 1.0  # 1 second ago
        assert bucket.consume() is None  # should succeed after refill


# =====================================================================
# Integration tests via FastAPI TestClient
# =====================================================================

class TestMeteringIntegration:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.db_path = str(tmp_path / "test_accounts.db")
        monkeypatch.setattr(
            "findata.server.db.config.ACCOUNTS_DB", self.db_path
        )
        monkeypatch.setenv("FINDATA_DATA_DIR", str(tmp_path / "findata-data"))

    def _make_app(self):
        from fastapi import Depends, FastAPI, Request
        from findata.server.auth import require_api_key
        from findata.server.quota import check_quota
        from findata.server.middleware.metering import MeteringMiddleware
        from findata.server.middleware.ratelimit import RateLimitMiddleware
        from findata.server.db.accounts_db import ensure_accounts_schema
        from findata.server.db.usage_db import ensure_usage_schema, get_usage_summary
        from findata.server.billing.plans import get_plan

        ensure_accounts_schema(self.db_path)
        ensure_usage_schema(self.db_path)

        test_app = FastAPI()

        # Add middleware
        test_app.add_middleware(MeteringMiddleware)
        test_app.add_middleware(RateLimitMiddleware)

        @test_app.get("/health")
        def health():
            return {"status": "ok"}

        _deps = [Depends(require_api_key), Depends(check_quota)]

        @test_app.get("/api/trades", dependencies=_deps)
        def trades():
            return {"trades": []}

        @test_app.get("/api/filings/chat", dependencies=_deps)
        def chat():
            return {"reply": "test"}

        @test_app.get("/api/usage", dependencies=[Depends(require_api_key)])
        def usage(request: Request):
            user = request.state.user
            plan = get_plan(user.get("plan", "free"))
            summary = get_usage_summary(user["user_id"], db_path=self.db_path)
            summary["plan"] = user.get("plan", "free")
            summary["credits_limit"] = plan.monthly_credits
            return summary

        return test_app

    def _create_user_and_key(self, email, plan="free"):
        from findata.server.db.accounts_db import create_user, create_api_key
        uid = create_user(email, plan=plan, db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)
        return uid, key

    def test_metering_records_usage(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import get_month_credits

        uid, key = self._create_user_and_key("meter@test.com")
        client = TestClient(self._make_app())
        resp = client.get("/api/trades", headers={"X-API-Key": key})
        assert resp.status_code == 200

        credits = get_month_credits(uid, db_path=self.db_path)
        assert credits == 1  # cache read = 1 credit

    def test_expensive_endpoint_records_more_credits(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import get_month_credits

        uid, key = self._create_user_and_key("expensive@test.com")
        client = TestClient(self._make_app())
        client.get("/api/filings/chat", headers={"X-API-Key": key})

        credits = get_month_credits(uid, db_path=self.db_path)
        assert credits == 20  # LLM call = 20 credits

    def test_owner_records_zero_credits(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import get_month_credits

        uid, key = self._create_user_and_key("owner@test.com", plan="owner")
        client = TestClient(self._make_app())
        client.get("/api/filings/chat", headers={"X-API-Key": key})

        credits = get_month_credits(uid, db_path=self.db_path)
        assert credits == 0  # owner is free

    def test_quota_exceeded_returns_429(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import record_usage

        uid, key = self._create_user_and_key("quota@test.com", plan="free")
        # Exhaust quota (free = 1000 credits)
        record_usage(uid, "/api/trades", 1000, 200, db_path=self.db_path)

        client = TestClient(self._make_app())
        resp = client.get("/api/trades", headers={"X-API-Key": key})
        assert resp.status_code == 429
        body = resp.json()
        assert body["detail"]["error"]["code"] == "QUOTA_EXCEEDED"

    def test_owner_not_quota_limited(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import record_usage

        uid, key = self._create_user_and_key("owner-nolimit@test.com", plan="owner")
        # Even with lots of recorded usage, owner should pass
        record_usage(uid, "/api/trades", 999999, 200, db_path=self.db_path)

        client = TestClient(self._make_app())
        resp = client.get("/api/trades", headers={"X-API-Key": key})
        assert resp.status_code == 200

    def test_usage_endpoint(self):
        from fastapi.testclient import TestClient

        uid, key = self._create_user_and_key("usage@test.com", plan="free")
        client = TestClient(self._make_app())

        # Make a call to generate usage
        client.get("/api/trades", headers={"X-API-Key": key})

        # Check usage endpoint
        resp = client.get("/api/usage", headers={"X-API-Key": key})
        assert resp.status_code == 200
        body = resp.json()
        assert body["plan"] == "free"
        assert body["credits_used"] >= 1
        assert body["credits_limit"] is not None

    def test_health_not_metered(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import get_month_credits

        uid, key = self._create_user_and_key("health@test.com")
        client = TestClient(self._make_app())
        client.get("/health")

        credits = get_month_credits(uid, db_path=self.db_path)
        assert credits == 0  # health is not metered
