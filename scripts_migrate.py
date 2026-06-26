import os
import glob
import re

DB_DIR = "findata/server/db"

def migrate():
    for filepath in glob.glob(os.path.join(DB_DIR, "*.py")):
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            
        basename = os.path.basename(filepath)
        if basename in ["engine.py", "config.py", "dbutil.py"]:
            continue
            
        # 1. Imports and connection
        if "import sqlite3" in content:
            content = content.replace("import sqlite3", "from findata.server.db.engine import connect\nimport psycopg2\nimport psycopg2.extras")
            
        content = content.replace("conn = sqlite3.connect(path)", "conn = connect(path)")
        content = content.replace("conn = sqlite3.connect(_db_path(db_path))", "conn = connect(path)")
        content = content.replace("conn = sqlite3.connect(path or _db_path())", "conn = connect(path)")
        content = content.replace("conn.row_factory = sqlite3.Row", "")
        
        # 2. Schema
        content = content.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        
        # 3. Specific SQL Dialect Fixes
        content = content.replace("INSERT OR IGNORE INTO users (email, plan, created_at) VALUES (?, ?, ?)", "INSERT INTO users (email, plan, created_at) VALUES (%s, %s, %s) ON CONFLICT (email) DO NOTHING")
        content = content.replace("PRAGMA journal_mode=WAL", "SELECT 1") # Postgres doesn't need WAL pragma
        content = content.replace("ON CONFLICT(user_id, period)", "ON CONFLICT (user_id, period)")
        
        # 4. ? to %s
        content = content.replace("?", "%s")
        
        # 5. Exceptions
        content = content.replace("sqlite3.OperationalError", "psycopg2.OperationalError")
        content = content.replace("sqlite3.Error", "psycopg2.Error")
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
            
if __name__ == "__main__":
    migrate()
