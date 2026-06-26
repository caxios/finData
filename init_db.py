import os
from dotenv import load_dotenv

load_dotenv()

def init_all():
    print("Initializing databases...")
    
    from findata.server.db.accounts_db import ensure_accounts_schema
    ensure_accounts_schema()
    print("[OK] Accounts schema created")
    
    from findata.server.db.usage_db import ensure_usage_schema
    ensure_usage_schema()
    print("[OK] Usage schema created")
    
    from findata.server.db.form4_db import init_db as init_form4
    init_form4("")
    print("[OK] Form4 schema created")
    
    from findata.server.db.company_facts_db import init_db as init_facts
    init_facts("")
    print("[OK] Company facts schema created")
    
    from findata.server.db.earnings_db import init_db as init_earnings
    init_earnings("")
    print("[OK] Earnings transcripts schema created")
    
    from findata.server.db.sec_10kq_db import init_db as init_10kq
    init_10kq("")
    print("[OK] 10-K/Q schema created")
    
    print("[DONE] All Postgres schemas successfully initialized!")

if __name__ == "__main__":
    init_all()
