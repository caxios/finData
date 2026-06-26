import sys
import os

# Add the current directory to sys.path so we can import findata
sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv
load_dotenv()

from findata.server.db.accounts_db import create_user, create_api_key

def main():
    print("Creating owner user...")
    user_id = create_user("owner@findata.local", "owner")
    print(f"User ID: {user_id}")
    
    print("Generating API Key...")
    api_key = create_api_key(user_id, "Test Key", env="live")
    print(f"\nYour API Key is:\n{api_key}\n")
    print("Keep this key safe! It will not be shown again.")

if __name__ == "__main__":
    main()
