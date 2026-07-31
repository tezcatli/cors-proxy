#!/usr/bin/env python3
"""Send Silence on Joue invitations via the /auth/invite endpoint.

Usage:
  python invite.py alice@example.com bob@example.com
  python invite.py --admin alice@example.com          # account is created as administrator
  python invite.py --url https://tezcat.fr --key MY_ADMIN_KEY alice@example.com

--admin is how the *first* administrator is bootstrapped; afterwards invitations
(and promotions) can be sent from the in-app console at /silence/admin/users.
"""

import argparse
import os
import sys
import urllib.request
import urllib.error
import json


def invite(base_url: str, admin_key: str, email: str, is_admin: bool = False) -> str:
    payload = json.dumps({"email": email, "is_admin": is_admin}).encode()
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/auth/invite",
        data=payload,
        headers={"Content-Type": "application/json", "X-Admin-Key": admin_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())["invite_url"]
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            msg = json.loads(body).get("error", body)
        except Exception:
            msg = body
        raise SystemExit(f"  ERROR {e.code}: {msg}")


def main():
    parser = argparse.ArgumentParser(description="Send Silence on Joue invitations")
    parser.add_argument("emails", nargs="+", metavar="EMAIL")
    parser.add_argument("--url", default=os.getenv("RESET_BASE_URL", "http://localhost:5000"),
                        help="Base URL of the backend (default: $RESET_BASE_URL or http://localhost:5000)")
    parser.add_argument("--key", default=os.getenv("ADMIN_KEY", ""),
                        help="Admin key (default: $ADMIN_KEY)")
    parser.add_argument("--admin", action="store_true",
                        help="Grant the administrator role to the accounts these invitations create")
    args = parser.parse_args()

    if not args.key:
        sys.exit("Admin key required: pass --key or set $ADMIN_KEY")

    ok = err = 0
    for email in args.emails:
        print(f"Inviting {email}{' as admin' if args.admin else ''} … ", end="", flush=True)
        try:
            url = invite(args.url, args.key, email, args.admin)
            print(f"OK\n  {url}")
            ok += 1
        except SystemExit as e:
            print(str(e))
            err += 1

    print(f"\n{ok} sent, {err} failed.")
    if err:
        sys.exit(1)


if __name__ == "__main__":
    main()
