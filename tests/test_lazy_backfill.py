"""
Tests for plan 05 — Lazy Fetch & Historical Backfill.

Covers:
- submissions JSON filtering (form type + date window) and shard overlap
- TickerNotFound for unknown tickers
- coverage table (record / get / is_covered enclosure)
- period-aware _lazy_load: backfill once, serve-from-coverage, per-window,
  422 on bad ticker, single-flight (exactly one fetch under concurrency)
- recent-N mode unchanged
- integration: cache-miss billed as higher-credit; 422 over HTTP
"""

import threading
import time

import pytest

from findata.sec.utils.form4 import form4_submissions as fs
from findata.server.db import form4_db as db
from findata.server.api import api_form4 as af


# ── helpers ─────────────────────────────────────────────────────────

def _fake_filing(ticker="MRVL", date="2019-06-01"):
    """A minimal parsed Form 4 dict that save_to_db can persist."""
    return {
        "source_url": f"http://example/{ticker}/{date}",
        "document_type": "4",
        "period_of_report": date,
        "ticker": ticker,
        "issuer": {"name": f"{ticker} Inc", "cik": "123", "trading_symbol": ticker},
        "reporting_owners": [{
            "name": "John Insider",
            "relationship": {
                "is_director": "1", "is_officer": "0", "is_ten_pct_owner": "0",
                "is_other": "0", "officer_title": "",
            },
        }],
        "transactions": [{
            "row_type": "nonDerivativeTransaction",
            "security_category": "non-derivative",
            "security_title": "Common Stock",
            "transaction_date": date,
            "transaction_code": "P",
            "transaction_code_description": "buy",
            "amount": "100",
            "acquired_or_disposed": "A",
            "price_per_share": "10",
            "shares_owned_after": "1000",
            "ownership_form": "D",
            "nature_of_ownership": "",
            "trade_ratio_pct": 1.0,
            "transaction_value": 1000.0,
            "market_value_after": 0,
            "market_cap": 0,
        }],
        "rss_meta": {"updated": date},
    }


# =====================================================================
# submissions JSON
# =====================================================================

class TestSubmissionsFilter:
    BLOCK = {
        "form": ["4", "10-K", "4/A", "4", "3"],
        "accessionNumber": ["0001-19-1", "0002-19-2", "0003-19-3", "0004-20-4", "0005-19-5"],
        "filingDate": ["2019-03-01", "2019-04-01", "2019-06-15", "2020-01-02", "2019-07-01"],
    }

    def test_filters_form_and_window(self):
        urls = fs._collect_form4_urls(320193, self.BLOCK, "2019-01-01", "2019-12-31")
        # only the two Form 4 / 4-A rows inside 2019
        assert len(urls) == 2
        assert all(d.startswith("2019") for d, _ in urls)

    def test_excludes_non_form4_and_out_of_window(self):
        urls = fs._collect_form4_urls(320193, self.BLOCK, "2019-01-01", "2019-12-31")
        dates = [d for d, _ in urls]
        assert "2020-01-02" not in dates  # out of window
        assert "2019-07-01" not in dates  # form '3', not 4

    def test_shard_overlap(self):
        assert fs._overlaps({"filingFrom": "2019-01-01", "filingTo": "2019-06-30"},
                            "2019-01-01", "2019-12-31") is True
        assert fs._overlaps({"filingFrom": "2001-01-01", "filingTo": "2018-12-31"},
                            "2019-01-01", "2019-12-31") is False

    def test_unknown_ticker_raises(self):
        with pytest.raises(fs.TickerNotFound):
            fs.fetch_form4_by_period("ZZZZ_NOT_A_TICKER", "2019-01-01", "2019-12-31")

    def test_fetch_uses_recent_and_overlapping_shards(self, monkeypatch):
        monkeypatch.setattr(fs, "lookup_cik", lambda t: ("0000320193", "APPLE INC"))
        root = {
            "filings": {
                "recent": {
                    "form": ["4"], "accessionNumber": ["0001-19-1"],
                    "filingDate": ["2019-05-01"],
                },
                "files": [
                    {"name": "shard-old.json", "filingFrom": "2001-01-01", "filingTo": "2010-12-31"},
                    {"name": "shard-2019.json", "filingFrom": "2019-01-01", "filingTo": "2019-04-30"},
                ],
            }
        }
        shard_2019 = {
            "form": ["4/A"], "accessionNumber": ["0009-19-9"], "filingDate": ["2019-02-02"],
        }

        fetched_shards = []

        def fake_get_json(url, timeout=30):
            if url.endswith("CIK0000320193.json"):
                return root
            fetched_shards.append(url)
            return shard_2019

        monkeypatch.setattr(fs, "_get_json", fake_get_json)
        monkeypatch.setattr(fs, "parse_form4", lambda u: {"source_url": u})

        out = fs.fetch_form4_by_period("AAPL", "2019-01-01", "2019-12-31", delay=0)
        # recent (1) + 2019 shard (1) = 2; old shard skipped (no overlap)
        assert len(out) == 2
        assert any("shard-2019.json" in u for u in fetched_shards)
        assert all("shard-old.json" not in u for u in fetched_shards)


# =====================================================================
# coverage table
# =====================================================================

class TestCoverage:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.db_path = str(tmp_path / "cov.db")

    def test_record_and_enclosure(self):
        db.record_coverage(self.db_path, "MRVL", "2019-01-01", "2019-12-31")
        assert db.is_covered(self.db_path, "MRVL", "2019-03-01", "2019-09-01")  # inside
        assert db.is_covered(self.db_path, "MRVL", "2019-01-01", "2019-12-31")  # exact
        assert not db.is_covered(self.db_path, "MRVL", "2018-01-01", "2018-12-31")  # outside
        assert not db.is_covered(self.db_path, "MRVL", "2019-06-01", "2020-06-01")  # partial

    def test_missing_table_is_not_covered(self, tmp_path):
        fresh = str(tmp_path / "empty.db")
        assert db.is_covered(fresh, "AAPL", "2019-01-01", "2019-12-31") is False


# =====================================================================
# period-aware _lazy_load
# =====================================================================

class TestLazyLoadPeriod:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.db_path = str(tmp_path / "all.db")
        monkeypatch.setitem(af.DB_PATHS, "all", self.db_path)
        self._mp = monkeypatch

    def test_backfill_then_served_from_coverage(self):
        calls = {"n": 0}

        def fake_fetch(ticker, lo, hi, **kw):
            calls["n"] += 1
            return [_fake_filing(ticker, "2019-06-01")]

        self._mp.setattr(af, "fetch_form4_by_period", fake_fetch)

        # First request → backfills
        n1 = af._lazy_load("all", ["MRVL"], 5, "2019-01-01", "2019-12-31")
        assert n1 == 1 and calls["n"] == 1
        assert db.is_covered(self.db_path, "MRVL", "2019-01-01", "2019-12-31")

        # Repeat → covered, no fetch
        n2 = af._lazy_load("all", ["MRVL"], 5, "2019-01-01", "2019-12-31")
        assert n2 == 0 and calls["n"] == 1

    def test_different_window_fetched_separately(self):
        calls = {"n": 0}
        self._mp.setattr(
            af, "fetch_form4_by_period",
            lambda t, lo, hi, **kw: (calls.__setitem__("n", calls["n"] + 1)
                                     or [_fake_filing(t, lo[:4] + "-06-01")]),
        )
        af._lazy_load("all", ["MRVL"], 5, "2019-01-01", "2019-12-31")
        af._lazy_load("all", ["MRVL"], 5, "2020-01-01", "2020-12-31")
        assert calls["n"] == 2  # each year fetched once

    def test_empty_window_records_coverage(self):
        # Company exists but no Form 4s in window → still record coverage so we
        # don't refetch forever.
        self._mp.setattr(af, "fetch_form4_by_period", lambda t, lo, hi, **kw: [])
        n1 = af._lazy_load("all", ["MRVL"], 5, "2005-01-01", "2005-12-31")
        assert n1 == 1
        assert db.is_covered(self.db_path, "MRVL", "2005-01-01", "2005-12-31")

    def test_invalid_ticker_raises_422(self):
        from fastapi import HTTPException

        def boom(t, lo, hi, **kw):
            raise fs.TickerNotFound(t)

        self._mp.setattr(af, "fetch_form4_by_period", boom)
        with pytest.raises(HTTPException) as exc:
            af._lazy_load("all", ["NOPE"], 5, "2019-01-01", "2019-12-31")
        assert exc.value.status_code == 422
        assert exc.value.detail["error"]["code"] == "INVALID_TICKER"

    def test_single_flight_one_fetch_under_concurrency(self):
        calls = {"n": 0}
        lock = threading.Lock()

        def slow_fetch(ticker, lo, hi, **kw):
            with lock:
                calls["n"] += 1
            time.sleep(0.05)  # hold the flight long enough for others to pile up
            return [_fake_filing(ticker, "2019-06-01")]

        self._mp.setattr(af, "fetch_form4_by_period", slow_fetch)

        threads = [
            threading.Thread(
                target=af._lazy_load,
                args=("all", ["MRVL"], 5, "2019-01-01", "2019-12-31"),
            )
            for _ in range(6)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert calls["n"] == 1  # exactly one upstream fetch


class TestLazyLoadRecentN:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.db_path = str(tmp_path / "all.db")
        monkeypatch.setitem(af.DB_PATHS, "all", self.db_path)
        self._mp = monkeypatch

    def test_recent_n_fetches_then_cached(self):
        calls = {"n": 0}
        self._mp.setattr(
            af, "parse_form4_for_ticker",
            lambda t, count=5: (calls.__setitem__("n", calls["n"] + 1)
                                or [_fake_filing(t, "2024-01-01")]),
        )
        # No date range → recent-N mode
        af._lazy_load("all", ["AAPL"], 5)
        assert calls["n"] == 1
        # Second call → rows exist → no fetch
        af._lazy_load("all", ["AAPL"], 5)
        assert calls["n"] == 1


# =====================================================================
# Integration — billing of cache miss + 422 over HTTP
# =====================================================================

class TestBackfillIntegration:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        self.acc_db = str(tmp_path / "accounts.db")
        self.trades_db = str(tmp_path / "watchlist.db")
        monkeypatch.setattr("findata.server.db.config.ACCOUNTS_DB", self.acc_db)
        monkeypatch.setenv("FINDATA_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setitem(af.DB_PATHS, "watchlist", self.trades_db)
        self._mp = monkeypatch

    def _make_app(self):
        from fastapi import Depends, FastAPI
        from findata.server.auth import require_api_key
        from findata.server.quota import check_quota
        from findata.server.middleware.metering import MeteringMiddleware
        from findata.server.db.accounts_db import ensure_accounts_schema
        from findata.server.db.usage_db import ensure_usage_schema

        ensure_accounts_schema(self.acc_db)
        ensure_usage_schema(self.acc_db)

        app = FastAPI()
        app.add_middleware(MeteringMiddleware)
        app.include_router(
            af.router, dependencies=[Depends(require_api_key), Depends(check_quota)]
        )
        return app

    def _user_key(self, email, plan="free"):
        from findata.server.db.accounts_db import create_user, create_api_key
        uid = create_user(email, plan=plan, db_path=self.acc_db)
        return uid, create_api_key(uid, db_path=self.acc_db)

    def test_cache_miss_billed_higher(self):
        from fastapi.testclient import TestClient
        from findata.server.db.usage_db import get_month_credits

        self._mp.setattr(
            af, "fetch_form4_by_period",
            lambda t, lo, hi, **kw: [_fake_filing(t, "2019-06-01")],
        )
        uid, key = self._user_key("backfill@test.com")
        client = TestClient(self._make_app())

        r = client.get(
            "/api/trades",
            params={"ticker": "MRVL", "source": "watchlist",
                    "date_from": "2019-01-01", "date_to": "2019-12-31"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 200
        # base 1 + LAZY_FETCH_CREDITS for the backfill
        assert get_month_credits(uid, db_path=self.acc_db) == 1 + af.LAZY_FETCH_CREDITS

        # Second identical request: covered → no fetch → only base credit added
        client.get(
            "/api/trades",
            params={"ticker": "MRVL", "source": "watchlist",
                    "date_from": "2019-01-01", "date_to": "2019-12-31"},
            headers={"X-API-Key": key},
        )
        assert get_month_credits(uid, db_path=self.acc_db) == (1 + af.LAZY_FETCH_CREDITS) + 1

    def test_invalid_ticker_returns_422(self):
        from fastapi.testclient import TestClient

        def boom(t, lo, hi, **kw):
            raise fs.TickerNotFound(t)

        self._mp.setattr(af, "fetch_form4_by_period", boom)
        _, key = self._user_key("badticker@test.com")
        client = TestClient(self._make_app())

        r = client.get(
            "/api/trades",
            params={"ticker": "NOPE", "source": "watchlist",
                    "date_from": "2019-01-01", "date_to": "2019-12-31"},
            headers={"X-API-Key": key},
        )
        assert r.status_code == 422
        assert r.json()["detail"]["error"]["code"] == "INVALID_TICKER"
