"""
Tests for plan 04 — Form 4 market-wide realtime polling worker.

Covers:
- master.idx Form 4 extraction + daily index URL building
- run_market_poll: success path (dedup counts, status) and failure resilience
- reconcile_daily_index: 404 (weekend) handling + happy path
- poller status observability
"""

from datetime import datetime, timezone

import pytest

from findata.server.ingestion import form4_poller as fp


@pytest.fixture(autouse=True)
def _reset_status():
    """Reset the module-level poller status between tests."""
    with fp._status_lock:
        fp._last_run.update({
            "last_poll_ts": None,
            "last_success_ts": None,
            "last_inserted": None,
            "last_skipped": None,
            "last_error": None,
            "consecutive_failures": 0,
            "total_polls": 0,
        })
    yield


# =====================================================================
# master.idx parsing + URL building
# =====================================================================

class TestMasterIdx:
    SAMPLE = (
        "Description line\n"
        "CIK|Company Name|Form Type|Date Filed|File Name\n"
        "-------------------------------------------------------\n"
        "1000045|ACME INC|4|2026-06-20|edgar/data/1000045/a.txt\n"
        "2000045|BETA CORP|10-K|2026-06-20|edgar/data/2000045/b.txt\n"
        "3000045|GAMMA LLC|4/A|2026-06-20|edgar/data/3000045/c.txt\n"
        "4000045|DELTA|4|2026-06-20|edgar/data/4000045/d.htm\n"
    )

    def test_extracts_only_form4_txt(self):
        urls = fp._parse_master_idx_for_form4(self.SAMPLE)
        assert urls == [
            "https://www.sec.gov/Archives/edgar/data/1000045/a.txt",
            "https://www.sec.gov/Archives/edgar/data/3000045/c.txt",
        ]

    def test_ignores_non_form4(self):
        # 10-K row and the .htm Form 4 row are excluded
        urls = fp._parse_master_idx_for_form4(self.SAMPLE)
        assert all("b.txt" not in u and "d.htm" not in u for u in urls)

    def test_empty_body(self):
        assert fp._parse_master_idx_for_form4("garbage\nno pipes here\n") == []

    def test_daily_index_url_quarter(self):
        url = fp._daily_master_index_url(datetime(2026, 6, 20, tzinfo=timezone.utc))
        assert url == (
            "https://www.sec.gov/Archives/edgar/daily-index/"
            "2026/QTR2/master.20260620.idx"
        )
        # Q1 boundary
        jan = fp._daily_master_index_url(datetime(2026, 1, 5, tzinfo=timezone.utc))
        assert "QTR1" in jan


# =====================================================================
# run_market_poll
# =====================================================================

class TestRunMarketPoll:
    def test_success_records_counts_and_status(self, monkeypatch):
        monkeypatch.setattr(fp, "parse_all_from_rss", lambda: [{"x": 1}])
        monkeypatch.setattr(fp, "save_to_db", lambda filings, db: (3, 97))

        inserted, skipped = fp.run_market_poll(db_path="ignored")
        assert (inserted, skipped) == (3, 97)

        status = fp.get_poller_status()
        assert status["last_inserted"] == 3
        assert status["last_skipped"] == 97
        assert status["last_error"] is None
        assert status["last_success_ts"] is not None
        assert status["total_polls"] == 1
        assert status["consecutive_failures"] == 0

    def test_dedup_second_cycle_inserts_zero(self, monkeypatch):
        # Simulate the same filings already present → all skipped
        monkeypatch.setattr(fp, "parse_all_from_rss", lambda: [{"x": 1}])
        monkeypatch.setattr(fp, "save_to_db", lambda filings, db: (0, 100))
        inserted, skipped = fp.run_market_poll(db_path="ignored")
        assert inserted == 0
        assert skipped == 100

    def test_failure_is_swallowed_and_recorded(self, monkeypatch):
        def boom():
            raise ConnectionError("network down")
        monkeypatch.setattr(fp, "parse_all_from_rss", boom)

        inserted, skipped = fp.run_market_poll(db_path="ignored")
        assert (inserted, skipped) == (0, 0)  # never raises

        status = fp.get_poller_status()
        assert status["consecutive_failures"] == 1
        assert "network down" in status["last_error"]
        assert status["last_success_ts"] is None


# =====================================================================
# reconcile_daily_index
# =====================================================================

class _FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text
        self.ok = 200 <= status_code < 300


class TestReconcile:
    def test_404_weekend_is_not_an_error(self, monkeypatch):
        monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _FakeResp(404))
        inserted, skipped = fp.reconcile_daily_index(date="2026-06-20", db_path="ignored")
        assert (inserted, skipped) == (0, 0)

    def test_happy_path_parses_and_saves(self, monkeypatch):
        body = (
            "CIK|Company Name|Form Type|Date Filed|File Name\n"
            "----\n"
            "1|ACME|4|2026-06-20|edgar/data/1/a.txt\n"
            "2|BETA|4/A|2026-06-20|edgar/data/2/b.txt\n"
        )
        monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _FakeResp(200, body))
        monkeypatch.setattr(fp, "parse_form4", lambda url: {"source_url": url})
        saved = {}
        def fake_save(parsed, db):
            saved["n"] = len(parsed)
            return (len(parsed), 0)
        monkeypatch.setattr(fp, "save_to_db", fake_save)

        inserted, skipped = fp.reconcile_daily_index(
            date="2026-06-20", db_path="ignored", delay=0,
        )
        assert inserted == 2
        assert saved["n"] == 2

    def test_bad_filing_is_skipped(self, monkeypatch):
        body = (
            "CIK|Company Name|Form Type|Date Filed|File Name\n"
            "1|ACME|4|2026-06-20|edgar/data/1/a.txt\n"
            "2|BETA|4|2026-06-20|edgar/data/2/b.txt\n"
        )
        monkeypatch.setattr(fp.requests, "get", lambda *a, **k: _FakeResp(200, body))

        def flaky_parse(url):
            if "a.txt" in url:
                raise ValueError("bad xml")
            return {"source_url": url}
        monkeypatch.setattr(fp, "parse_form4", flaky_parse)
        monkeypatch.setattr(fp, "save_to_db", lambda parsed, db: (len(parsed), 0))

        inserted, _ = fp.reconcile_daily_index(
            date="2026-06-20", db_path="ignored", delay=0,
        )
        assert inserted == 1  # only the good one survived


# =====================================================================
# Health route mechanism
# =====================================================================

class TestPollerHealthRoute:
    def test_status_exposed_via_route(self, monkeypatch):
        import os
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()

        @app.get("/api/health/poller")
        def poller_health():
            status = fp.get_poller_status()
            enabled = os.getenv("ENABLE_FORM4_POLLER", "0") == "1"
            return {"enabled": enabled, **status}

        monkeypatch.setattr(fp, "parse_all_from_rss", lambda: [])
        monkeypatch.setattr(fp, "save_to_db", lambda f, db: (0, 0))
        fp.run_market_poll(db_path="ignored")

        resp = TestClient(app).get("/api/health/poller")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enabled"] is False
        assert body["total_polls"] == 1
        assert "last_success_ts" in body
