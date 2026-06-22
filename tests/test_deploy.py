"""
Tests for plan 08 — Deployment artifacts (repo-level, no cloud).

Covers:
- /api/download-pdf gated off by default (Playwright not required to import app)
- worker entrypoint wiring (starts scheduler + runs poller loop)
- packaging: universe.json ships with the package; deploy artifacts exist
"""

import os
from pathlib import Path

import pytest


_ROOT = Path(__file__).resolve().parents[1]


# =====================================================================
# /api/download-pdf gating (Playwright pitfall)
# =====================================================================

class TestPdfGate:
    def test_disabled_by_default_returns_503(self, monkeypatch):
        from fastapi import HTTPException
        from findata.server.api import api_10kq
        monkeypatch.delenv("ENABLE_PDF_DOWNLOAD", raising=False)
        with pytest.raises(HTTPException) as exc:
            api_10kq.generate_pdf("https://example.com/x")
        assert exc.value.status_code == 503
        assert exc.value.detail["error"]["code"] == "PDF_DISABLED"

    def test_playwright_not_imported_at_module_load(self):
        import sys
        import importlib
        # Re-import the module and confirm it doesn't pull playwright at import.
        importlib.reload(importlib.import_module("findata.server.api.api_10kq"))
        # The lazy import lives inside generate_pdf; module import must not require it.
        # (If playwright were a top-level import, importing the app would fail on
        # hosts without it.) We assert the source has no top-level import.
        src = (_ROOT / "findata" / "server" / "api" / "api_10kq.py").read_text(encoding="utf-8")
        top_level = [ln for ln in src.splitlines()
                     if ln.startswith("from playwright") or ln.startswith("import playwright")]
        assert top_level == []


# =====================================================================
# worker entrypoint
# =====================================================================

class TestWorker:
    def test_main_starts_scheduler_and_poller(self, monkeypatch):
        import findata.server.worker as worker
        from findata.server.ingestion import form4_poller, scheduled
        from findata.server.db import config as dbconfig

        calls = {"sched": 0, "poll": 0, "dirs": 0}
        monkeypatch.setattr(dbconfig, "ensure_data_dirs",
                            lambda: calls.__setitem__("dirs", calls["dirs"] + 1))
        monkeypatch.setattr(scheduled, "start_background_scheduler",
                            lambda **k: calls.__setitem__("sched", calls["sched"] + 1))
        monkeypatch.setattr(form4_poller, "run_loop",
                            lambda **k: calls.__setitem__("poll", calls["poll"] + 1))

        worker.main()
        assert calls == {"sched": 1, "poll": 1, "dirs": 1}

    def test_intervals_from_env(self, monkeypatch):
        import findata.server.worker as worker
        from findata.server.ingestion import form4_poller, scheduled
        from findata.server.db import config as dbconfig

        captured = {}
        monkeypatch.setattr(dbconfig, "ensure_data_dirs", lambda: None)
        monkeypatch.setattr(scheduled, "start_background_scheduler",
                            lambda **k: captured.update(sched=k))
        monkeypatch.setattr(form4_poller, "run_loop",
                            lambda **k: captured.update(poll=k))
        monkeypatch.setenv("FORM4_POLL_INTERVAL", "123")
        monkeypatch.setenv("SCHED_10KQ_INTERVAL", "456")
        monkeypatch.setenv("SCHED_DART_INTERVAL", "789")

        worker.main()
        assert captured["poll"]["poll_interval"] == 123
        assert captured["sched"]["kq_interval"] == 456
        assert captured["sched"]["dart_interval"] == 789


# =====================================================================
# packaging / deploy artifacts
# =====================================================================

class TestPackagingArtifacts:
    def test_universe_json_ships_with_package(self):
        # The data universe must be importable resource data (so a non-editable
        # Docker install has it). Loading via the module path proves it's present.
        from findata.server.ingestion import universe
        assert len(universe.get_us_universe()) > 0

    def test_deploy_files_exist(self):
        for rel in ["Dockerfile", ".dockerignore", "README.md",
                    ".github/workflows/ci.yml", "infra/README.md"]:
            assert (_ROOT / rel).exists(), f"missing deploy artifact: {rel}"

    def test_dockerignore_excludes_secrets(self):
        text = (_ROOT / ".dockerignore").read_text(encoding="utf-8")
        assert ".env" in text  # secrets never baked into the image
