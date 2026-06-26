import pytest

@pytest.fixture(autouse=True, scope="session")
def setup_test_db_schema():
    """Ensure all schemas are created before any tests run."""
    import os
    from findata.server.db.config import DATABASE_URL
    if not DATABASE_URL:
        # If no DB URL is provided (e.g. locally without .env), we can't test.
        # But we assume the CI sets it up.
        pass
    
    # We must mock init_db for some modules if they expect an API key but we don't care here, 
    # but init_all handles it.
    try:
        from findata.server.db.accounts_db import ensure_accounts_schema
        from findata.server.db.usage_db import ensure_usage_schema
        from findata.server.db.form4_db import init_db as init_form4
        from findata.server.db.company_facts_db import init_db as init_facts
        from findata.server.db.earnings_db import init_db as init_earnings
        from findata.server.db.sec_10kq_db import init_db as init_10kq
        
        ensure_accounts_schema()
        ensure_usage_schema()
        init_form4("")
        init_facts("")
        init_earnings("")
        init_10kq("")
    except Exception as e:
        print(f"Failed to initialize schemas: {e}")

@pytest.fixture(autouse=True)
def clean_db():
    """Truncate all tables before every test to ensure perfect isolation."""
    from findata.server.db.engine import connect
    from findata.server.db.config import DATABASE_URL
    
    if not DATABASE_URL:
        return
        
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL and "findata_test" not in DATABASE_URL:
        # SAFETY GUARD: Do not truncate production/remote databases!
        print("WARNING: Skipping test DB cleanup because DATABASE_URL does not look like a local test database.")
        return
        
    try:
        conn = connect()
        # Clean accounts and usage
        conn.execute("TRUNCATE TABLE users, api_keys, api_usage CASCADE")
        # Clean form4
        conn.execute("TRUNCATE TABLE _form4_schema_meta, form4_documents, form4_non_derivative_transactions, form4_derivative_transactions, raw_filings CASCADE")
        # Clean facts
        conn.execute("TRUNCATE TABLE _facts_schema_meta, company_tickers, facts CASCADE")
        # Clean earnings
        conn.execute("TRUNCATE TABLE _earnings_schema_meta, earnings_transcripts CASCADE")
        # Clean 10kq
        conn.execute("TRUNCATE TABLE _sec10kq_schema_meta, sec_10kq_filings CASCADE")
    except Exception as e:
        # If a table doesn't exist yet or other errors, ignore
        pass
