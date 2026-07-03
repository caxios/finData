import os
import subprocess
import sys
import textwrap
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


def _project_optional_dependencies() -> dict[str, list[str]]:
    with PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]["optional-dependencies"]


def _run_import_check(code: str, data_dir: Path) -> str:
    env = os.environ.copy()
    env["FINDATA_DATA_DIR"] = str(data_dir)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_server_app_import_does_not_create_data_dir(tmp_path):
    data_dir = tmp_path / "findata-data"
    output = _run_import_check(
        """
        import os
        from pathlib import Path

        import findata.server.app

        print(Path(os.environ["FINDATA_DATA_DIR"]).exists())
        """,
        data_dir,
    )
    assert output == "False"


def test_ensure_data_dirs_creates_server_directories(tmp_path):
    data_dir = tmp_path / "findata-data"
    output = _run_import_check(
        """
        import os
        from pathlib import Path

        from findata.server.db.config import ensure_data_dirs

        ensure_data_dirs()
        root = Path(os.environ["FINDATA_DATA_DIR"])
        print((root / "sec_db").is_dir())
        print((root / "data").is_dir())
        """,
        data_dir,
    )
    assert output.splitlines() == ["True", "True"]


def test_legacy_sec_app_warns_and_reexports_server_app(tmp_path):
    output = _run_import_check(
        """
        import warnings

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", DeprecationWarning)
            import findata.sec.app as legacy
            import findata.server.app as canonical

        print(legacy.app is canonical.app)
        print(any("deprecated" in str(w.message) for w in caught))
        """,
        tmp_path / "findata-data",
    )
    assert output.splitlines() == ["True", "True"]


def test_legacy_sec_api_reexports_server_router(tmp_path):
    output = _run_import_check(
        """
        import warnings

        warnings.simplefilter("ignore", DeprecationWarning)
        from findata.sec.api import api_form4 as legacy
        from findata.server.api import api_form4 as canonical

        print(legacy.router is canonical.router)
        """,
        tmp_path / "findata-data",
    )
    assert output == "True"


def test_server_extra_includes_full_server_router_dependencies():
    extras = _project_optional_dependencies()
    server_deps = set(extras["server"])

    assert {
        "fastapi",
        "uvicorn",
        "playwright",
        "tavily-python",
        "psycopg2-binary",
    } <= server_deps


def test_all_extra_reuses_server_extra():
    extras = _project_optional_dependencies()

    assert extras["all"] == ["findata[server,sec-parser]"]
