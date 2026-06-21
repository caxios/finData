"""
Admin CLI for issuing findata API keys.

Usage::

    # Create owner account + key
    python -m findata.server.tools.issue_key --email me@example.com --plan owner

    # Create a free-tier user key
    python -m findata.server.tools.issue_key --email user@example.com

    # Create a key with a label
    python -m findata.server.tools.issue_key --email user@example.com --label "production"

    # List keys for a user
    python -m findata.server.tools.issue_key --email user@example.com --list
"""

import argparse
import sys

from findata.server.db.accounts_db import (
    create_api_key,
    create_user,
    ensure_accounts_schema,
    list_keys_for_user,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Issue and manage findata API keys.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  # Create owner account with a key
  python -m findata.server.tools.issue_key --email me@x.com --plan owner

  # Create a free-tier key with a label
  python -m findata.server.tools.issue_key --email user@x.com --label "my app"

  # List keys for an existing user
  python -m findata.server.tools.issue_key --email user@x.com --list
""",
    )
    parser.add_argument(
        "--email",
        required=True,
        help="User email address (creates user if not exists).",
    )
    parser.add_argument(
        "--plan",
        default="free",
        choices=["owner", "free", "pro"],
        help="Billing plan for the user (default: free).",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Optional human-readable label for the key.",
    )
    parser.add_argument(
        "--env",
        default="live",
        choices=["live", "test"],
        help="Key environment: 'live' or 'test' (default: live).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_keys",
        help="List existing keys for the user instead of creating one.",
    )

    args = parser.parse_args()

    ensure_accounts_schema()

    user_id = create_user(args.email, plan=args.plan)

    if args.list_keys:
        keys = list_keys_for_user(user_id)
        if not keys:
            print(f"No keys found for {args.email}")
            return
        print(f"\nKeys for {args.email}:")
        print("-" * 70)
        for k in keys:
            status = "ACTIVE" if k["active"] else "INACTIVE"
            label = k["label"] or "(no label)"
            print(
                f"  {k['key_prefix']}...  [{status}]  "
                f"label={label}  created={k['created_at']}  "
                f"last_used={k['last_used_at'] or 'never'}"
            )
        return

    plaintext_key = create_api_key(user_id, label=args.label, env=args.env)

    print()
    print("=" * 60)
    print("  API KEY CREATED SUCCESSFULLY")
    print("=" * 60)
    print()
    print(f"  Email:  {args.email}")
    print(f"  Plan:   {args.plan}")
    print(f"  Label:  {args.label or '(none)'}")
    print(f"  Env:    {args.env}")
    print()
    print(f"  Key:    {plaintext_key}")
    print()
    print("  ⚠️  SAVE THIS KEY NOW — it will NOT be shown again.")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
