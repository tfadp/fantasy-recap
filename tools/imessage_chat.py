#!/usr/bin/env python3
"""
Pull the league group chat out of iMessage into prompts/<league>-chat.md.

iMessage has no export button, but macOS keeps every message in a SQLite
database at ~/Library/Messages/chat.db. This reads it, read-only, and writes
the one thread you point it at.

    # 1. find the thread
    python3 tools/imessage_chat.py list

    # 2. dump it (chat id from step 1)
    python3 tools/imessage_chat.py dump 42 --limit 800 > prompts/mop-chat.md

Nothing is uploaded and nothing leaves the machine. The output file is
gitignored; it reaches the scheduled run as the MOP_CHAT secret and never
touches the public repo.

**Terminal needs Full Disk Access**, or the open fails with "unable to open
database file" or "operation not permitted":

    System Settings -> Privacy & Security -> Full Disk Access -> add Terminal
    (or iTerm, or whichever app you run this from), then restart it.
"""

import argparse
import os
import sqlite3
import sys
import datetime

DB = os.path.expanduser("~/Library/Messages/chat.db")
# Apple counts from 2001-01-01, in nanoseconds on modern macOS.
APPLE_EPOCH = datetime.datetime(2001, 1, 1)


def connect():
    if not os.path.exists(DB):
        sys.exit(f"No iMessage database at {DB}. Is this a Mac with Messages set up?")
    try:
        # read-only, so there is no way for this to disturb Messages
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        sys.exit(f"Could not open the database ({e}).\n\n"
                 f"This is almost always Full Disk Access. Grant it to your\n"
                 f"terminal in System Settings -> Privacy & Security -> Full\n"
                 f"Disk Access, then restart the terminal and try again.")


def when(raw):
    if not raw:
        return ""
    secs = raw / 1e9 if raw > 1e11 else raw
    try:
        return (APPLE_EPOCH + datetime.timedelta(seconds=secs)).strftime("%Y-%m-%d")
    except Exception:
        return ""


def body(text, blob):
    """
    Messages written on newer macOS leave `text` NULL and put the content in
    `attributedBody`, an NSKeyedArchiver typedstream. Skipping those loses most
    of a modern thread, so pull the string back out of the blob.
    """
    if text:
        return text
    if not blob:
        return None
    try:
        chunk = blob.split(b"NSString")[1][5:]
        if chunk[0] == 0x81:
            length = int.from_bytes(chunk[1:3], "little")
            chunk = chunk[3:]
        else:
            length, chunk = chunk[0], chunk[1:]
        return chunk[:length].decode("utf-8", errors="replace")
    except Exception:
        return None


def cmd_list(args):
    con = connect()
    rows = con.execute("""
        SELECT c.ROWID, c.display_name, c.chat_identifier,
               COUNT(m.ROWID) AS n, MAX(m.date) AS last
        FROM chat c
        JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        JOIN message m ON m.ROWID = cmj.message_id
        GROUP BY c.ROWID
        HAVING n >= ?
        ORDER BY n DESC
        LIMIT ?
    """, (args.min_messages, args.limit)).fetchall()
    if not rows:
        sys.exit("No chats found.")
    print(f"{'id':>6}  {'msgs':>7}  {'last':<12}  name")
    print("-" * 72)
    for cid, name, ident, n, last in rows:
        label = name or ident or "(unnamed group)"
        print(f"{cid:>6}  {n:>7}  {when(last):<12}  {label[:44]}")
    print("\nGroup chats usually have no display name and a long chat_identifier.")
    print("Pick the one with the message count that looks like your league, then:")
    print("  python3 tools/imessage_chat.py dump <id> > prompts/mop-chat.md")


def cmd_dump(args):
    con = connect()
    rows = con.execute("""
        SELECT m.date, h.id, m.is_from_me, m.text, m.attributedBody
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        LEFT JOIN handle h ON h.ROWID = m.handle_id
        WHERE cmj.chat_id = ?
        ORDER BY m.date DESC
        LIMIT ?
    """, (args.chat_id, args.limit)).fetchall()
    if not rows:
        sys.exit(f"No messages in chat {args.chat_id}.")

    out = ["# How this league actually talks",
           "",
           "Real messages, pulled from iMessage. This is the voice reference:",
           "the running bits, the nicknames, who mocks who and how they take it.",
           "Not for quoting back verbatim.",
           ""]
    for date, handle, is_me, text, blob in reversed(rows):
        msg = (body(text, blob) or "").strip()
        if not msg:
            continue
        who = "me" if is_me else (handle or "unknown")
        out.append(f"[{when(date)}] {who}: {msg}")
    print("\n".join(out))
    kept = len(out) - 6
    print(f"\n{kept} messages written.", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="show chats, biggest first, to find the league thread")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--min-messages", type=int, default=50)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("dump", help="write one chat to stdout")
    p.add_argument("chat_id", type=int)
    p.add_argument("--limit", type=int, default=800,
                   help="most recent N messages (default 800)")
    p.set_defaults(fn=cmd_dump)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
