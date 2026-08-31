#!/usr/bin/env python3
"""
Run this once, after Yahoo approves your API access.

    export YAHOO_CLIENT_ID=...
    export YAHOO_CLIENT_SECRET=...
    python3 setup_yahoo.py

It prints a Yahoo link, you approve, you paste the code back, and it writes
oauth2.json. From then on the token refreshes itself and you never touch it
again unless you change your Yahoo password or revoke the app.

Then run:  python3 setup_yahoo.py --leagues     to find your league key.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(HERE, "oauth2.json")


def authorize():
    cid = os.environ.get("YAHOO_CLIENT_ID")
    secret = os.environ.get("YAHOO_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("Set YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET first.")
    with open(TOKEN_FILE, "w") as f:
        json.dump({"consumer_key": cid, "consumer_secret": secret}, f)
    from yahoo_oauth import OAuth2
    oauth = OAuth2(None, None, from_file=TOKEN_FILE)   # prompts in the terminal
    if oauth.token_is_valid():
        print(f"Authorized. Token saved to {TOKEN_FILE}.")
        print("Keep this file private. It is a key to your Yahoo fantasy account.")


def show_leagues():
    sys.path.insert(0, HERE)
    from adapters import yahoo
    season = sys.argv[2] if len(sys.argv) > 2 else "2026"
    for lg in yahoo.list_leagues(season):
        print(f"  {lg['league_key']}  {lg['name']}")
    print("\nPut the league_key into leagues.json as league_id.")


if __name__ == "__main__":
    if "--leagues" in sys.argv:
        show_leagues()
    else:
        authorize()
