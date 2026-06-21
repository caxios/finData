"""
Tests for plan 03 — Billing & Margin Pricing (Track A foundation).

Covers:
- Pricing model in billing/plans.py (plan→price, credits→USD, margin)
- Track 0 upstream cost measurement (estimators + recording + summaries)
- Cost guardrail / circuit breaker (09 §3.5) on paid-upstream endpoints
- Gateway shared-secret trust (Track A), with owner exemption
"""

import pytest


# =====================================================================
# Pricing model — billing/plans.py
# =====================================================================

class TestPricingModel:
    def test_owner_and_free_are_zero_price(self):
        from findata.server.billing.plans import get_plan_price
        assert get_plan_price("owner") == 0.0
        assert get_plan_price("free") == 0.0

    def test_pro_has_a_price(self):
        from findata.server.billing.plans import get_plan_price
        assert get_plan_price("pro") > 0.0

    def test_credits_to_usd(self):
        from findata.server.billing.plans import credits_to_usd, USD_PER_CREDIT
        assert credits_to_usd(1000) == round(1000 * USD_PER_CREDIT, 6)

    def test_price_with_margin_applies_markup(self):
        from findata.server.billing.plans import price_with_margin, MARGIN
        assert price_with_margin(1.0) == round(1.0 * (1 + MARGIN), 6)
        assert price_with_margin(1.0) > 1.0

    def test_unknown_plan_price_falls_back(self):
        from findata.server.billing.plans import get_plan_price
        # unknown → default (free) → 0.0
        assert get_plan_price("does-not-exist") == 0.0


# =====================================================================
# Track 0 — upstream cost estimators
# =====================================================================

class TestUpstreamEstimators:
    def test_tavily_transcript_cost_positive(self):
        from findata.server.billing.upstream_cost import tavily_transcript_usd
        assert tavily_transcript_usd() > 0
        # more extracts → higher cost
        assert tavily_transcript_usd(4) > tavily_transcript_usd(1)

    def test_llm_cost_scales_with_tokens(self):
        from findata.server.billing.upstream_cost import llm_cost_usd
        small = llm_cost_usd(1000, 100)
        big = llm_cost_usd(100000, 10000)
        assert big > small > 0

    def test_unknown_model_falls_back_to_default(self):
        from findata.server.billing.upstream_cost import llm_cost_usd
        # unknown model should not raise; uses default pricing
        assert llm_cost_usd(1000, 100, model="totally-unknown") > 0


# =====================================================================
# Track 0 — recording + summaries
# =====================================================================

class TestUpstreamRecording:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.db_path = str(tmp_path / "test_upstream.db")

    def test_record_and_month_total(self):
        from findata.server.billing.upstream_cost import (
            record_transcript_cost, record_chat_cost, get_month_upstream_usd,
        )
        c1 = record_transcript_cost(user_id=1, db_path=self.db_path)
        c2 = record_chat_cost(user_id=1, db_path=self.db_path)
        total = get_month_upstream_usd(db_path=self.db_path)
        assert total == pytest.approx(round(c1 + c2, 6))

    def test_summary_has_avg_per_call(self):
        from findata.server.billing.upstream_cost import (
            record_chat_cost, get_upstream_cost_summary,
        )
        record_chat_cost(user_id=1, db_path=self.db_path)
        record_chat_cost(user_id=2, db_path=self.db_path)
        summary = get_upstream_cost_summary(db_path=self.db_path)
        chat = [e for e in summary["endpoints"] if e["endpoint"] == "/api/filings/chat"][0]
        assert chat["calls"] == 2
        assert chat["avg_usd_per_call"] > 0

    def test_measured_chat_cost_when_tokens_given(self):
        from findata.server.billing.upstream_cost import (
            record_chat_cost, llm_cost_usd,
        )
        cost = record_chat_cost(
            user_id=1, input_tokens=5000, output_tokens=500, db_path=self.db_path
        )
        assert cost == llm_cost_usd(5000, 500)


# =====================================================================
# Integration — guardrail + gateway via TestClient
# =====================================================================

class TestGuardrailAndGateway:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.db_path = str(tmp_path / "test_accounts.db")
        monkeypatch.setattr("findata.server.db.config.ACCOUNTS_DB", self.db_path)
        monkeypatch.setenv("FINDATA_DATA_DIR", str(tmp_path / "findata-data"))
        self._monkeypatch = monkeypatch

    def _make_app(self):
        from fastapi import Depends, FastAPI
        from findata.server.auth import require_api_key, require_gateway
        from findata.server.quota import check_quota
        from findata.server.billing.guardrail import circuit_breaker
        from findata.server.db.accounts_db import ensure_accounts_schema
        from findata.server.db.usage_db import ensure_usage_schema
        from findata.server.billing.upstream_cost import ensure_upstream_schema

        ensure_accounts_schema(self.db_path)
        ensure_usage_schema(self.db_path)
        ensure_upstream_schema(self.db_path)

        test_app = FastAPI()
        deps = [
            Depends(require_api_key),
            Depends(require_gateway),
            Depends(check_quota),
            Depends(circuit_breaker),
        ]

        @test_app.get("/api/trades", dependencies=deps)
        def trades():
            return {"trades": []}

        @test_app.get("/api/transcript", dependencies=deps)
        def transcript():
            return {"transcript": "..."}

        return test_app

    def _user_and_key(self, email, plan="free"):
        from findata.server.db.accounts_db import create_user, create_api_key
        uid = create_user(email, plan=plan, db_path=self.db_path)
        key = create_api_key(uid, db_path=self.db_path)
        return uid, key

    # ── Circuit breaker ──────────────────────────────────────────────

    def test_breaker_trips_on_paid_endpoint_when_over_budget(self):
        from fastapi.testclient import TestClient
        from findata.server.billing.upstream_cost import record_chat_cost

        self._monkeypatch.setenv("FINDATA_UPSTREAM_MONTHLY_BUDGET_USD", "0.01")
        # Spend past the budget
        for _ in range(5):
            record_chat_cost(user_id=1, db_path=self.db_path)

        _, key = self._user_and_key("breaker@test.com")
        client = TestClient(self._make_app())

        # Cache endpoint still works
        assert client.get("/api/trades", headers={"X-API-Key": key}).status_code == 200
        # Paid endpoint is tripped
        resp = client.get("/api/transcript", headers={"X-API-Key": key})
        assert resp.status_code == 503
        assert resp.json()["detail"]["error"]["code"] == "UPSTREAM_BUDGET_EXCEEDED"

    def test_breaker_disabled_when_no_budget(self):
        from fastapi.testclient import TestClient
        from findata.server.billing.upstream_cost import record_chat_cost

        self._monkeypatch.delenv("FINDATA_UPSTREAM_MONTHLY_BUDGET_USD", raising=False)
        for _ in range(5):
            record_chat_cost(user_id=1, db_path=self.db_path)

        _, key = self._user_and_key("nobudget@test.com")
        client = TestClient(self._make_app())
        assert client.get("/api/transcript", headers={"X-API-Key": key}).status_code == 200

    def test_owner_bypasses_breaker(self):
        from fastapi.testclient import TestClient
        from findata.server.billing.upstream_cost import record_chat_cost

        self._monkeypatch.setenv("FINDATA_UPSTREAM_MONTHLY_BUDGET_USD", "0.01")
        for _ in range(5):
            record_chat_cost(user_id=1, db_path=self.db_path)

        _, key = self._user_and_key("owner-breaker@test.com", plan="owner")
        client = TestClient(self._make_app())
        assert client.get("/api/transcript", headers={"X-API-Key": key}).status_code == 200

    # ── Gateway trust ────────────────────────────────────────────────

    def test_gateway_required_for_non_owner(self):
        from fastapi.testclient import TestClient

        self._monkeypatch.setenv("FINDATA_GATEWAY_SECRET", "s3cr3t")
        _, key = self._user_and_key("gw@test.com")
        client = TestClient(self._make_app())

        # No gateway secret → 403
        resp = client.get("/api/trades", headers={"X-API-Key": key})
        assert resp.status_code == 403
        assert resp.json()["detail"]["error"]["code"] == "GATEWAY_REQUIRED"

        # Correct gateway secret → 200
        ok = client.get(
            "/api/trades",
            headers={"X-API-Key": key, "X-Gateway-Secret": "s3cr3t"},
        )
        assert ok.status_code == 200

    def test_owner_bypasses_gateway(self):
        from fastapi.testclient import TestClient

        self._monkeypatch.setenv("FINDATA_GATEWAY_SECRET", "s3cr3t")
        _, key = self._user_and_key("owner-gw@test.com", plan="owner")
        client = TestClient(self._make_app())

        # Owner reaches origin directly (no gateway secret) → 200
        resp = client.get("/api/trades", headers={"X-API-Key": key})
        assert resp.status_code == 200

    def test_no_gateway_secret_configured_is_noop(self):
        from fastapi.testclient import TestClient

        self._monkeypatch.delenv("FINDATA_GATEWAY_SECRET", raising=False)
        _, key = self._user_and_key("gw-off@test.com")
        client = TestClient(self._make_app())
        assert client.get("/api/trades", headers={"X-API-Key": key}).status_code == 200
