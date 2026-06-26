import sys
import os
import argparse

# Add the current directory to sys.path so we can import findata
sys.path.insert(0, os.path.abspath("."))

from dotenv import load_dotenv
load_dotenv()

from findata.server.db.accounts_db import create_user, create_api_key, list_keys_for_user, deactivate_key
from findata.server.db.engine import connect

def get_user_by_email(email: str):
    from findata.server.db.engine import connect
    from findata.server.db import config
    conn = connect(config.DATABASE_URL)
    row = conn.execute("SELECT id, plan FROM users WHERE email = %s", (email,)).fetchone()
    conn.close()
    if row:
        return {"id": row[0], "plan": row[1]}
    return None

def cmd_create(email, plan, label):
    user = get_user_by_email(email)
    if user:
        user_id = user["id"]
        print(f"User '{email}' already exists (ID: {user_id}). Generating a new key for this user.")
    else:
        user_id = create_user(email, plan)
        print(f"Created new user '{email}' (ID: {user_id}).")
        
    api_key = create_api_key(user_id, label, env="live")
    print("\n" + "="*50)
    print(f"🎉 NEW API KEY FOR {email}:")
    print(api_key)
    print("="*50 + "\n")
    print("⚠️  IMPORTANT: Copy this key now. For security, it is encrypted in the database and cannot be viewed again!")

def cmd_list(email):
    user = get_user_by_email(email)
    if not user:
        print(f"User '{email}' not found.")
        return
    
    keys = list_keys_for_user(user["id"])
    print(f"\nAPI Keys for {email}:")
    for k in keys:
        status = "🟢 Active" if k["active"] else "🔴 Revoked"
        print(f"- ID: {k['id']} | Prefix: {k['key_prefix']}... | Label: {k['label']} | Status: {status} | Created: {k['created_at']}")

def cmd_revoke(key_id):
    deactivate_key(key_id)
    print(f"Key ID {key_id} has been permanently revoked.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FinData API Key Manager")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Create command
    parser_create = subparsers.add_parser("create", help="Create a new API key for a user")
    parser_create.add_argument("email", help="User's email (e.g. friend@gmail.com)")
    parser_create.add_argument("--plan", default="free", help="Billing plan (free, pro, owner)")
    parser_create.add_argument("--label", default="Default Key", help="Label for this key")
    
    # List command
    parser_list = subparsers.add_parser("list", help="List all keys for a user")
    parser_list.add_argument("email", help="User's email")
    
    # Revoke command
    parser_revoke = subparsers.add_parser("revoke", help="Revoke (disable) a specific API key")
    parser_revoke.add_argument("key_id", type=int, help="The ID of the key to revoke")
    
    args = parser.parse_args()
    
    if args.command == "create":
        cmd_create(args.email, args.plan, args.label)
    elif args.command == "list":
        cmd_list(args.email)
    elif args.command == "revoke":
        cmd_revoke(args.key_id)
    else:
        parser.print_help()
