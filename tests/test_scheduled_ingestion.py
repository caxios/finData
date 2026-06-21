"""
Tests for plan 06 — Scheduled Ingestion & Cache Freshness.

Covers:
- universe config (load, env override, upper/dedup, missing file)
- centralized freshness/TTL + company_data reads from it
- throttle helpers (chunked, run_with_backoff)
- run_10kq_refresh (universe-driven, mocked pipeline)
- run_dart_refresh (chunking/throttle, mocked module runners)
- scheduler run_once + DART-deps-missing handling + env gating
- warmup orchestration
"""

import json

import pytest


# =====================================================================
# universe
# =====================================================================

class TestUniverse:
    def test_default_universe_loads(self):
        from findata.server.ingestion import universe
        assert len(universe.get_us_universe()) > 0
        assert len(universe.get_kr_universe()) > 0

    def test_upper_and_dedup(self, tmp_path, monkeypatch):
        from findata.server.ingestion import universe
        f = tmp_path / "u.json"
        f.write_text(json.dumps({"us": ["aapl", "AAPL", "msft"], "kr": ["삼성", "삼성"]}),
                     encoding="utf-8")
        monkeypatch.setenv("FINDATA_UNIVERSE_FILE", str(f))
        assert universe.get_us_universe() == ["AAPL", "MSFT"]
        assert universe.get_kr_universe() == ["삼성"]

    def test_missing_file_is_empty(self, tmp_path, monkeypatch):
        from findata.server.ingestion import universe
        monkeypatch.setenv("FINDATA_UNIVERSE_FILE", str(tmp_path / "nope.json"))
        assert universe.get_us_universe() == []
        assert universe.load_universe() == {}


# =====================================================================
# freshness
# =====================================================================

class TestFreshness:
    def test_get_ttl_days(self):
        from findata.server.ingestion import freshness
        assert freshness.get_ttl_days("10kq") == 90
        assert freshness.get_ttl_days("form4") == 7
        assert freshness.get_ttl_days("unknown") == freshness.DEFAULT_TTL_DAYS

    def test_is_within_ttl(self):
        from datetime import datetime, timedelta
        from findata.server.ingestion import freshness
        recent = (datetime.utcnow() - timedelta(days=3)).strftime("%Y-%m-%d")
        old = (datetime.utcnow() - timedelta(days=400)).strftime("%Y-%m-%d")
        assert freshness.is_within_ttl(recent, "form4") is True
        assert freshness.is_within_ttl(old, "form4") is False
        assert freshness.is_within_ttl(None, "form4") is False

    def test_company_data_uses_centralized_ttl(self):
        import findata.server.company_data as cd
        from findata.server.ingestion import freshness
        assert cd.TTL_10KQ_DAYS == freshness.get_ttl_days("10kq")
        assert cd.TTL_FORM4_DAYS == freshness.get_ttl_days("form4")


# =====================================================================
# throttle
# =====================================================================

class TestThrottle:
    def test_chunked(self):
        from findata.server.ingestion.throttle import chunked
        assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
        assert list(chunked([1, 2, 3], 0)) == [[1, 2, 3]]  # size<=0 → one chunk
        assert list(chunked([], 3)) == []

    def test_backoff_retries_then_succeeds(self):
        from findata.server.ingestion.throttle import run_with_backoff
        calls = {"n": 0}
        slept = []

        def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("quota")
            return "ok"

        out = run_with_backoff(flaky, retries=5, base_delay=1.0, sleep=slept.append)
        assert out == "ok"
        assert calls["n"] == 3
        assert slept == [1.0, 2.0]  # exponential

    def test_non_retryable_raises_immediately(self):
        from findata.server.ingestion.throttle import run_with_backoff
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise ValueError("fatal")

        with pytest.raises(ValueError):
            run_with_backoff(boom, retries=3, is_retryable=lambda e: False,
                             sleep=lambda s: None)
        assert calls["n"] == 1

    def test_exhausts_retries(self):
        from findata.server.ingestion.throttle import run_with_backoff
        with pytest.raises(RuntimeError):
            run_with_backoff(lambda: (_ for _ in ()).throw(RuntimeError("x")),
                             retries=2, sleep=lambda s: None)


# =====================================================================
# run_10kq_refresh (mocked pipeline)
# =====================================================================

class TestRun10kqRefresh:
    def test_refresh_runs_pipeline_for_universe(self, monkeypatch):
        from findata.server.ingestion import sec_10kq_ingest as ing

        monkeypatch.setattr(
            ing, "fetch_and_resolve",
            lambda cik, count: [{"document_url": "u", "accession_number": "a"}],
        )
        monkeypatch.setattr(
            ing, "parse_single_filing",
            lambda filing: {"sections": {"business": "x"},
                            "form_type": "10-K", "filing_date": "2024-01-01"},
        )
        saved = {}
        monkeypatch.setattr(
            ing, "save_batch",
            lambda rows, db: (saved.__setitem__("n", len(rows)) or (len(rows), 0)),
        )
        monkeypatch.setattr(ing, "get_filing_count", lambda db: 1)

        ing.run_10kq_refresh(universe=["AAPL"], count=2)
        assert saved.get("n") == 1  # one parsed filing saved

    def test_unresolvable_ticker_skipped(self, monkeypatch):
        from findata.server.ingestion import sec_10kq_ingest as ing
        called = {"n": 0}
        monkeypatch.setattr(
            ing, "fetch_and_resolve",
            lambda cik, count: called.__setitem__("n", called["n"] + 1) or [],
        )
        # Unknown ticker resolves to no CIK → pipeline gets empty watchlist
        ing.run_10kq_refresh(universe=["ZZZZ_NOPE"], count=1)
        assert called["n"] == 0


# =====================================================================
# run_dart_refresh (mocked runners)
# =====================================================================

class TestRunDartRefresh:
    def test_chunks_and_runs_modules(self, monkeypatch):
        from findata.server.ingestion import dart_batch as db

        monkeypatch.setattr(
            db, "_resolve_corp_codes",
            lambda names: {"A": "001", "B": "002", "C": "003"},
        )
        calls = {"accounts": 0, "indicators": 0}
        monkeypatch.setattr(db, "run_accounts",
                            lambda codes, **k: calls.__setitem__("accounts", calls["accounts"] + 1))
        monkeypatch.setattr(db, "run_indicators",
                            lambda codes, **k: calls.__setitem__("indicators", calls["indicators"] + 1))

        summary = db.run_dart_refresh(
            universe=["A", "B", "C"], modules=["accounts", "indicators"],
            chunk_size=2, delay=0,
        )
        assert summary["companies"] == 3
        assert summary["chunks"] == 2          # ceil(3/2)
        assert calls["accounts"] == 2          # once per chunk
        assert calls["indicators"] == 2

    def test_empty_universe(self, monkeypatch):
        from findata.server.ingestion import dart_batch as db
        monkeypatch.setattr(db, "_resolve_corp_codes", lambda names: {})
        summary = db.run_dart_refresh(universe=["X"], modules=["accounts"], delay=0)
        assert summary["companies"] == 0

    def test_quota_error_is_retried(self, monkeypatch):
        from findata.server.ingestion import dart_batch as db
        monkeypatch.setattr(db, "_resolve_corp_codes", lambda names: {"A": "001"})
        attempts = {"n": 0}

        def flaky_accounts(codes, **k):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise RuntimeError("rate limit exceeded")  # _is_quota_error → retry

        monkeypatch.setattr(db, "run_accounts", flaky_accounts)
        db.run_dart_refresh(universe=["A"], modules=["accounts"],
                            chunk_size=10, delay=0, base_delay=0)
        assert attempts["n"] == 2  # retried once then succeeded


# =====================================================================
# scheduler + warmup
# =====================================================================

class TestScheduler:
    def test_run_once_calls_both(self, monkeypatch):
        from findata.server.ingestion import scheduled
        calls = []
        monkeypatch.setattr(scheduled, "refresh_10kq", lambda count=5: calls.append("kq"))
        monkeypatch.setattr(scheduled, "refresh_dart", lambda: calls.append("dart"))
        scheduled.run_once()
        assert calls == ["kq", "dart"]

    def test_refresh_dart_handles_missing_deps(self, monkeypatch):
        from findata.server.ingestion import scheduled, dart_batch
        def raise_missing():
            raise ModuleNotFoundError("No module named 'dart_fss'")
        monkeypatch.setattr(dart_batch, "run_dart_refresh", lambda *a, **k: raise_missing())
        # Should not raise; records an error in status
        scheduled.refresh_dart()
        assert "dart deps missing" in (scheduled.get_scheduler_status()["last_error"] or "")


class TestWarmup:
    def test_warmup_runs_both(self, monkeypatch):
        from findata.server.ingestion import warmup, sec_10kq_ingest, dart_batch
        monkeypatch.setattr(sec_10kq_ingest, "run_10kq_refresh", lambda **k: None)
        monkeypatch.setattr(dart_batch, "run_dart_refresh", lambda **k: {"companies": 3})
        result = warmup.run_warmup()
        assert result["us"] == "ok"
        assert result["kr"] == {"companies": 3}

    def test_warmup_kr_deps_missing(self, monkeypatch):
        from findata.server.ingestion import warmup, sec_10kq_ingest, dart_batch
        monkeypatch.setattr(sec_10kq_ingest, "run_10kq_refresh", lambda **k: None)
        def raise_missing(**k):
            raise ModuleNotFoundError("dart_fss")
        monkeypatch.setattr(dart_batch, "run_dart_refresh", raise_missing)
        result = warmup.run_warmup()
        assert result["us"] == "ok"
        assert "skipped" in result["kr"]


class TestAppGating:
    def test_scheduler_not_started_without_flag(self, monkeypatch):
        import findata.server.app as app
        monkeypatch.delenv("ENABLE_SCHEDULED_INGESTION", raising=False)
        app._scheduler_stop = None
        app._maybe_start_scheduled_ingestion()
        assert app._scheduler_stop is None

    def test_scheduler_started_with_flag(self, monkeypatch):
        import findata.server.app as app
        from findata.server.ingestion import scheduled
        monkeypatch.setenv("ENABLE_SCHEDULED_INGESTION", "1")
        sentinel = object()
        monkeypatch.setattr(scheduled, "start_background_scheduler", lambda: sentinel)
        app._scheduler_stop = None
        app._maybe_start_scheduled_ingestion()
        assert app._scheduler_stop is sentinel
        app._scheduler_stop = None  # cleanup
