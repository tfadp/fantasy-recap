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

import env
import publish

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
LIMIT = 990

# urllib announces itself as "Python-urllib/3.x", which Cloudflare blocks in
# front of Resend with a 403 (error 1010) before the request ever reaches the
# API. Nothing to do with the key. Send a real user agent.
UA = "fantasy-recap/1.0 (+https://github.com/tfadp/fantasy-recap)"


def latest_recaps():
    found = []
    for cfg in json.load(open(os.path.join(HERE, "leagues.json")))["leagues"]:
        files = sorted(glob.glob(os.path.join(OUT, cfg["name"], "*.md")))
        if files:
            with open(files[-1]) as f:
                found.append((cfg.get("display_name", cfg["name"]), f.read(), files[-1]))
    return found


def stem_of(path):
    return os.path.basename(path)[:-3]  # drop ".md"


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
            headers={"Content-Type": "application/json", "User-Agent": UA})
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
        headers={"Content-Type": "application/json", "User-Agent": UA,
                 "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status < 300


def page_link(stem=None):
    """
    The URL to paste into the thread. A week that has not been approved yet
    lives at its unguessable draft path, so this returns that instead: you get
    something you can actually open on your phone at 9am without it being the
    link the league sees.
    """
    base = os.environ.get("PAGES_URL")
    if not base:
        repo = os.environ.get("GITHUB_REPOSITORY")  # owner/name, set by Actions
        if repo and "/" in repo:
            owner, name = repo.split("/", 1)
            base = f"https://{owner}.github.io/{name}"
    if not base:
        return None, False
    base = base.rstrip("/")
    if stem is None:
        return base + "/", True
    if stem in publish.approved():
        return f"{base}/{stem}.html", True
    return f"{base}/drafts/{publish.draft_name(stem)}", False


def main():
    env.load()
    recaps = latest_recaps()
    if not recaps:
        sys.exit("Nothing to deliver. Did run.py write a recap?")

    for name, text, path in recaps:
        stem = stem_of(path)
        link, is_public = page_link(stem)
        state = "" if is_public else " [DRAFT]"

        body = text
        if link:
            body = (f"{'Link to send' if is_public else 'Draft link (only you have it)'}:\n"
                    f"{link}\n\n"
                    f"{'-' * 40}\n"
                    f"Text, ready to copy into the thread:\n\n{text}\n")
            if not is_public:
                body += (f"\n{'-' * 40}\n"
                         f"Happy with it?   ./recap approve {stem}\n"
                         f"Want it redone?  ./recap redo --week "
                         f"{int(stem.split('-wk')[1])} --note \"...\"\n")

        sent, problems = [], []

        def attempt(label, fn):
            # The recap is already written and published by this point. A
            # provider being down must not turn that into a traceback and an
            # empty Tuesday; report it and fall through to printing.
            try:
                if fn():
                    sent.append(label)
            except Exception as exc:
                problems.append(f"{label}: {exc}")

        # GroupMe only fires for a week you have already approved; a draft is
        # not something to accidentally broadcast.
        if is_public:
            attempt("GroupMe", lambda: groupme(
                f"{name}\n\n{text}" + (f"\n{link}" if link else "")))
        attempt("email", lambda: email(
            f"{name} — Week {stem.split('-wk')[1].lstrip('0')} recap{state}", body))
        for pr in problems:
            print(f"  delivery failed, {pr}", file=sys.stderr)
        print(f"{name}: {', '.join(sent) or 'printed only'}  ({path})")
        if not sent:
            print(body)
        elif link:
            print(f"  {link}")


if __name__ == "__main__":
    main()
