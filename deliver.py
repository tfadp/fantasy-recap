#!/usr/bin/env python3
"""
Last step: get the finished write-ups to the league.

GroupMe: create a bot at https://dev.groupme.com/bots/new, pick your league
group, and copy the bot id into GROUPME_BOT_ID. GroupMe caps a message at
1000 characters, so a long recap is split and sent in order.

Email: set RESEND_API_KEY and RECAP_EMAIL_TO (comma separated).

If neither is configured this just prints, which is the right behavior when
you want to read the draft before the league does.
"""

import glob
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
LIMIT = 990


def latest_recaps():
    found = []
    for cfg in json.load(open(os.path.join(HERE, "leagues.json")))["leagues"]:
        files = sorted(glob.glob(os.path.join(OUT, cfg["name"], "*.md")))
        if files:
            with open(files[-1]) as f:
                found.append((cfg.get("display_name", cfg["name"]), f.read(), files[-1]))
    return found


def chunk(text, limit=LIMIT):
    """Split on paragraph breaks so a joke never lands across two messages."""
    parts, cur = [], ""
    for para in text.split("\n\n"):
        if len(cur) + len(para) + 2 <= limit:
            cur = f"{cur}\n\n{para}" if cur else para
        else:
            if cur:
                parts.append(cur)
            while len(para) > limit:
                cut = para.rfind(" ", 0, limit)
                cut = cut if cut > limit * 0.6 else limit
                parts.append(para[:cut])
                para = para[cut:].lstrip()
            cur = para
    if cur:
        parts.append(cur)
    return parts


def groupme(text):
    bot = os.environ.get("GROUPME_BOT_ID")
    if not bot:
        return False
    for part in chunk(text):
        req = urllib.request.Request(
            "https://api.groupme.com/v3/bots/post",
            data=json.dumps({"bot_id": bot, "text": part}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            if r.status not in (200, 201, 202):
                raise RuntimeError(f"GroupMe returned {r.status}")
    return True


def email(subject, text):
    key = os.environ.get("RESEND_API_KEY")
    to = [x.strip() for x in (os.environ.get("RECAP_EMAIL_TO") or "").split(",") if x.strip()]
    if not key or not to:
        return False
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps({"from": "recap@resend.dev", "to": to,
                         "subject": subject, "text": text}).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status < 300


def page_link():
    """The URL to paste into the message thread, if Pages is set up."""
    base = os.environ.get("PAGES_URL")
    if base:
        return base.rstrip("/") + "/"
    repo = os.environ.get("GITHUB_REPOSITORY")  # owner/name, set by Actions
    if repo and "/" in repo:
        owner, name = repo.split("/", 1)
        return f"https://{owner}.github.io/{name}/"
    return None


def main():
    recaps = latest_recaps()
    if not recaps:
        sys.exit("Nothing to deliver. Did run.py write a recap?")

    link = page_link()
    for name, text, path in recaps:
        body = text
        if link:
            body = (f"{text}\n\n"
                    f"---\nPaste this into the thread:\n{link}\n")
        sent = []
        if groupme(f"{name}\n\n{text}" + (f"\n{link}" if link else "")):
            sent.append("GroupMe")
        if email(f"{name} recap", body):
            sent.append("email")
        print(f"{name}: {', '.join(sent) or 'printed only'}  ({path})")
        if not sent:
            print(body)
    if link:
        print(f"\nWeb version: {link}")


if __name__ == "__main__":
    main()
