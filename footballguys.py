"""
Parse a footballguys daily email into structured advice.

Dan gets one of these every morning from bryant@footballguys.com. Each email
inlines ONE article in full (e.g. the week's top waiver pickups) and links out
to the rest (upgrades/downgrades, injury report, etc.). This module pulls both
out so the Tuesday recommendation can lean on the whole week's advice:

  parse_picks(text) -> the inlined article's player recommendations
  parse_links(text) -> the table-of-contents links, real URLs recovered
  parse_email(...)  -> both of the above, bundled with subject/date
  store_daily(...)  -> append one day's parse to that week's file
  load_week(...)    -> read a week's accumulated days back

Design rule, same as the recap: code computes, the model writes. This module
only extracts what footballguys actually said; it never decides an add/drop.

PRIVACY: footballguys is a paid service and this repo is public. The parsed
content is written only to history/footballguys/, which is gitignored. Never
commit it, and never put real article text in a committed test.

Stdlib only, like the rest of the Sleeper path.
"""
import base64
import binascii
import json
import re
from pathlib import Path

# The positions footballguys tags a pick with. Requiring one of these is what
# separates a real "Name (POS-TEAM)" headline from an incidental "text (note)".
FANTASY_POSITIONS = {"QB", "RB", "WR", "TE", "K", "DEF", "DST", "D/ST"}

# "Madeup Runner (RB-DEN)" -> name / pos / team. Name is non-greedy so the LAST
# "(POS-TEAM)" wins; team is 2-4 letters (LAC, NYJ, etc.).
_PICK_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<pos>[A-Za-z/]{1,4})-(?P<team>[A-Za-z]{2,4})\)$")

# "Bid Recommendation: 25-50% of Annual FAAB Budget" -> the bid text. Gmail's
# plain text has no asterisks; an earlier rendering wrapped the line in them,
# so both are accepted.
_BID_RE = re.compile(r"^\*?\s*Bid Recommendation:\s*(?P<bid>.+?)\s*\*?$")

# Gmail underlines each headline with a row of dashes on the next line. It is
# decoration, not reasoning.
_UNDERLINE_RE = re.compile(r"^-{3,}$")

# One bullet of the "Upgrades, Downgrades, and Waiver Wire Wonders" list:
#   "* RB Braelon Allen NYJ (waiver wire: 10-20%)"
#   "* RB Rachaad White WAS (waiver wire: DROP FOR 5-10% OR HIGHER)"
#   "* QB Bo Nix DEN"
_PRIORITY_ROW_RE = re.compile(
    r"^\*\s+(?P<pos>[A-Za-z/]{1,4})\s+(?P<name>.+?)\s+(?P<team>[A-Z]{2,4})"
    r"(?:\s+\(waiver wire:\s*(?P<tail>[^)]+)\))?$")
_DROP_RE = re.compile(r"(?i)^DROP FOR\s+(?P<pct>\S+)\s+OR HIGHER$")
# "Running Back Upgrades" / "Tight End Downgrades" -> which way the list points.
_PRIORITY_HEADER_RE = re.compile(r"(?i)^[A-Za-z ]+\s(?P<dir>Upgrades|Downgrades)$")

# A link that sits alone on its own line inside angle brackets, e.g. "<https://...>".
_URL_LINE_RE = re.compile(r"^<(?P<url>https?://\S+)>$")

# The header that opens footballguys' table of contents ("Inside This Issue").
_TOC_HEADER_RE = re.compile(r"(?i)^(in|inside)\s+this\s+issue")


def decode_tracking_url(url: str) -> str | None:
    """Recover the real footballguys URL from a convertkit tracking link.

    Convertkit wraps the destination as base64 in the final path segment. We try
    both standard and url-safe base64, with padding restored, and only accept a
    result that actually looks like a URL. Returns None if it can't be decoded
    (e.g. a plain link that was never wrapped) rather than raising.
    """
    segment = url.rstrip("/").rsplit("/", 1)[-1]
    if not segment:
        return None
    padded = segment + "=" * (-len(segment) % 4)
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded = decoder(padded).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if decoded.startswith("http://") or decoded.startswith("https://"):
            return decoded
    return None


def parse_picks(text: str) -> list[dict]:
    """Extract the inlined article's player recommendations.

    Walks the email line by line. A line matching "Name (POS-TEAM)" (with a real
    fantasy position) starts a new pick; a following "*Bid Recommendation: ...*"
    line fills its bid; every other non-empty line until the next headline is
    reasoning. Returns a list of
        {name, pos, nfl_team, bid_recommendation, reasoning}
    in the order they appear.
    """
    picks: list[dict] = []
    current: dict | None = None
    reasoning_lines: list[str] = []

    def _flush() -> None:
        if current is not None:
            current["reasoning"] = " ".join(reasoning_lines).strip()
            picks.append(current)

    for raw_line in text.splitlines():
        line = raw_line.strip()

        headline = _PICK_RE.match(line)
        if headline and headline.group("pos").upper() in FANTASY_POSITIONS:
            _flush()
            current = {
                "name": headline.group("name").strip(),
                "pos": headline.group("pos").upper(),
                "nfl_team": headline.group("team").upper(),
                "bid_recommendation": None,
                "reasoning": "",
            }
            reasoning_lines = []
            continue

        if current is None:
            continue  # still in the intro, before the first pick

        # A pick's reasoning is prose. It ends where the table-of-contents/footer
        # begins: a bracketed URL line, a "- " list item, or an "Inside This
        # Issue" header. Without this the final pick (no headline after it) would
        # swallow the entire footer and link list as "reasoning". We null the
        # current pick rather than break, so a stray marker only truncates one
        # pick's reasoning and never drops the picks that follow it.
        if (_URL_LINE_RE.match(line) or line.startswith("- ") or line.startswith("-->")
                or _TOC_HEADER_RE.match(line)):
            _flush()
            current = None
            continue

        if _UNDERLINE_RE.match(line):
            continue

        bid = _BID_RE.match(line)
        if bid:
            current["bid_recommendation"] = bid.group("bid").strip()
            continue

        if line:
            reasoning_lines.append(line)

    _flush()
    return picks


def parse_priority_list(text: str) -> list[dict]:
    """Extract the "Upgrades, Downgrades, and Waiver Wire Wonders" list.

    Walks the email line by line. A "<Position> Upgrades" or "<Position>
    Downgrades" header sets the direction; each "* POS Name TEAM (...)" bullet
    under it becomes a row. Returns a list of
        {name, pos, nfl_team, direction, bid, drop_for}
    where bid is the "(waiver wire: 10-20%)" figure on an upgrade, and drop_for
    is the "DROP FOR 5-10% OR HIGHER" figure on a downgrade. Either is None
    when the bullet carries no waiver-wire tail.
    """
    rows: list[dict] = []
    direction: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()

        header = _PRIORITY_HEADER_RE.match(line)
        if header:
            direction = header.group("dir").lower()[:-1]  # "Upgrades" -> "upgrade"
            continue
        if direction is None:
            continue

        row = _PRIORITY_ROW_RE.match(line)
        if not row or row.group("pos").upper() not in FANTASY_POSITIONS:
            continue

        tail = (row.group("tail") or "").strip()
        drop = _DROP_RE.match(tail)
        rows.append({
            "name": row.group("name").strip(),
            "pos": row.group("pos").upper(),
            "nfl_team": row.group("team").upper(),
            "direction": direction,
            "bid": tail if tail and not drop else None,
            "drop_for": drop.group("pct") if drop else None,
        })
    return rows


def parse_links(text: str) -> list[dict]:
    """Extract the table-of-contents links, with real footballguys URLs restored.

    In the plaintext each article shows as a title line ("- Upgrades and
    Downgrades"), then the tracking link alone on the next line ("<https://...>").
    We pair each bracketed URL with the nearest preceding "- " title and decode
    the tracking link. Returns
        {title, url, tracking_url}
    where url is the decoded footballguys link (or the tracking link if it could
    not be decoded).
    """
    lines = text.splitlines()
    links: list[dict] = []
    for i, raw_line in enumerate(lines):
        match = _URL_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        tracking_url = match.group("url")

        title = None
        for j in range(i - 1, -1, -1):
            prev = lines[j].strip()
            if prev.startswith("- "):
                title = prev[2:].strip()
                break
            if prev:  # a non-empty, non-title line means no title precedes this
                break

        real = decode_tracking_url(tracking_url)
        links.append({
            "title": title,
            "url": real or tracking_url,
            "tracking_url": tracking_url,
        })
    return links


def parse_email(text: str, subject: str | None = None, received_date: str | None = None) -> dict:
    """Bundle one email's picks and links with its subject and date."""
    return {
        "subject": subject,
        "date": received_date,
        "picks": parse_picks(text),
        "priority": parse_priority_list(text),
        "links": parse_links(text),
    }


def _week_file(season: str, week: int, out_dir: Path) -> Path:
    return Path(out_dir) / f"{season}-wk{week:02d}.json"


def store_daily(parsed: dict, season: str, week: int, out_dir: str | Path = "history/footballguys") -> Path:
    """Append one day's parsed email to that week's accumulation file.

    A week's worth of daily emails collects in one JSON file (a list of daily
    parses). Entries are keyed by date, so re-processing the same day replaces
    that day rather than adding a duplicate. Returns the file path written.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = _week_file(season, week, out_dir)

    days: list[dict] = []
    if path.exists():
        days = json.loads(path.read_text(encoding="utf-8"))

    days = [d for d in days if d.get("date") != parsed.get("date")]
    days.append(parsed)
    days.sort(key=lambda d: d.get("date") or "")

    path.write_text(json.dumps(days, indent=2), encoding="utf-8")
    return path


def load_week(season: str, week: int, out_dir: str | Path = "history/footballguys") -> list[dict]:
    """Read back a week's accumulated daily emails (empty list if none yet)."""
    path = _week_file(season, week, Path(out_dir))
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))
