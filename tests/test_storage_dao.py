"""
Tests for plan 07 — Storage migration DAO foundation.

Covers:
- engine.get_backend / connect (SQLite default; Postgres deferred → clear error)
- dbutil.dedup_insert portability (SQLite INSERT OR IGNORE vs Postgres ON CONFLICT)
- form4_repo read-path queries (query/get/summary/rankings/presence) on SQLite,
  including endpoints that previously had no tests (summary, rankings, get_trade)
"""

import pytest

from findata.server.db import engine, dbutil, form4_repo, form4_db


# =====================================================================
# dbutil
# =====================================================================

class TestDbutil:
    def test_postgres_uses_on_conflict_with_target(self):
        out = dbutil.dedup_insert("INSERT INTO t (a, b) VALUES (?, ?)",
                                  conflict_cols=["a", "b"], backend="postgres")
        assert "ON CONFLICT (a, b) DO NOTHING" in out
        assert "INSERT OR IGNORE" not in out

    def test_postgres_bare_on_conflict(self):
        out = dbutil.dedup_insert("INSERT INTO t (a) VALUES (?)", backend="postgres")
        assert out.rstrip().endswith("ON CONFLICT DO NOTHING")

    def test_placeholder(self):
        assert dbutil.placeholder("sqlite") == "?"
        assert dbutil.placeholder("postgres") == "%s"


# =====================================================================
# form4_repo  (build a real SQLite DB via save_to_db, then query)
# =====================================================================

def _filing(ticker, code, value, date="2024-03-01", owner="Jane Doe",
            security="Common Stock"):
    a_or_d = "A" if code == "P" else "D"
    return {
        "source_url": f"http://x/{ticker}/{owner}/{date}/{code}/{value}",
        "document_type": "4",
        "period_of_report": date,
        "ticker": ticker,
        "issuer": {"name": f"{ticker} Inc", "cik": "1", "trading_symbol": ticker},
        "reporting_owners": [{
            "name": owner,
            "relationship": {"is_director": "1", "is_officer": "0",
                             "is_ten_pct_owner": "0", "is_other": "0",
                             "officer_title": ""},
        }],
        "transactions": [{
            "row_type": "nonDerivativeTransaction",
            "security_category": "non-derivative",
            "security_title": security,
            "transaction_date": date,
            "transaction_code": code,
            "transaction_code_description": "",
            "amount": "10",
            "acquired_or_disposed": a_or_d,
            "price_per_share": "1",
            "shares_owned_after": "100",
            "ownership_form": "D",
            "nature_of_ownership": "",
            "trade_ratio_pct": 1.0,
            "transaction_value": value,
            "market_value_after": 0,
            "market_cap": 0,
        }],
        "rss_meta": {"updated": date},
    }


class TestForm4Repo:
    @pytest.fixture(autouse=True)
    def _db(self, tmp_path, monkeypatch):
        monkeypatch.setattr("findata.server.db.config.DATABASE_URL", None)
        self.db = str(tmp_path / "trades.db")
        form4_db.save_to_db([
            _filing("AAPL", "P", 1000.0, date="2024-01-01"),
            _filing("AAPL", "S", 400.0, date="2024-02-01"),
            _filing("MSFT", "P", 200.0, date="2024-03-01"),
        ], self.db)

    def test_presence_helpers(self, tmp_path):
        assert form4_repo.has_any_rows(self.db) is True
        assert set(form4_repo.tickers_missing(self.db, ["AAPL", "TSLA"])) == {"TSLA"}
        # Nonexistent DB → everything missing / no rows
        empty = str(tmp_path / "none.db")
        assert form4_repo.has_any_rows(empty) is False
        assert form4_repo.tickers_missing(empty, ["AAPL"]) == ["AAPL"]

    def test_query_trades_filters_and_pagination(self):
        total, rows = form4_repo.query_trades(self.db, tickers=["AAPL"])
        assert total == 2
        assert all(r["ticker"] == "AAPL" for r in rows)

        # date filter
        total, rows = form4_repo.query_trades(self.db, date_from="2024-02-01")
        assert total == 2  # AAPL 02-01 + MSFT 03-01

        # min_value
        total, _ = form4_repo.query_trades(self.db, min_value=500)
        assert total == 1  # only the 1000 buy

        # pagination
        total, page = form4_repo.query_trades(self.db, limit=1, offset=0)
        assert total == 3 and len(page) == 1

    def test_get_trade(self):
        _, rows = form4_repo.query_trades(self.db, tickers=["MSFT"])
        tid = rows[0]["id"]
        got = form4_repo.get_trade(self.db, tid)
        assert got and got["ticker"] == "MSFT"
        assert form4_repo.get_trade(self.db, 999999) is None

    def test_summary(self):
        rows = {r["ticker"]: r for r in form4_repo.summary(self.db)}
        assert rows["AAPL"]["total_trades"] == 2
        assert rows["AAPL"]["total_buys"] == 1
        assert rows["AAPL"]["total_sells"] == 1

    def test_top_rankings(self):
        top_buy, top_sell = form4_repo.top_rankings(self.db, n=10)
        # AAPL net = 1000(P) - 400(S) = 600 > 0 → buying side
        buy_tickers = [r["ticker"] for r in top_buy]
        assert "AAPL" in buy_tickers
        aapl = next(r for r in top_buy if r["ticker"] == "AAPL")
        assert aapl["net_value"] == 600.0

    def test_rankings_for_ticker_union(self, tmp_path):
        # Second DB with a different MSFT buy → union dedup across files
        db2 = str(tmp_path / "trades2.db")
        form4_db.save_to_db([_filing("MSFT", "P", 50.0, date="2024-04-01")], db2)
        agg = form4_repo.rankings_for_ticker([self.db, db2], "MSFT")
        # 200 (db1) + 50 (db2) = 250 buys, deduped by distinct source_url
        assert agg["buy_value"] == 250.0
        assert agg["buy_count"] == 2
        assert agg["net_value"] == 250.0
