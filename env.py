"""
Keys live in a gitignored .env next to this file, so a public repo never sees
them and you are not re-exporting variables into every shell.

    ANTHROPIC_API_KEY=sk-ant-...
    RESEND_API_KEY=re_...
    RECAP_EMAIL_TO=you@example.com
    PAGES_URL=https://tfadp.github.io/fantasy-recap

Real environment variables always win, which is what makes the same code work
unchanged under GitHub Actions where the values arrive as secrets.
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
DOTENV = os.path.join(HERE, ".env")


def load(path=DOTENV):
    if not os.path.exists(path):
        return {}
    found = {}
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            found[k] = v
            os.environ.setdefault(k, v)
    return found
