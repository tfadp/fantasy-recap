"""
Tests for the footballguys email parser.

Same style as the other tests: plain asserts, stdlib only, run with
    python3 test_footballguys.py

IMPORTANT: every fixture below uses INVENTED players and URLs. Footballguys is a
paid service and this repo is public, so no real article text lives here. The
parser is proven against the real email locally (history/footballguys/, which is
gitignored), never in a committed test.
"""
import base64
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import footballguys  # noqa: E402  (import after sys.path setup, like the other tests)


# A stand-in for the "top waiver pickups" article that footballguys inlines in
# full. Structure matches the real email exactly: a player headline line of the
# form "Name (POS-TEAM)", a blank line, an italic "*Bid Recommendation: ...*"
# line, then one or more reasoning lines, repeating per pick.
FEATURE_SAMPLE = """The Top Waiver Wire Pickups of Sample Week

By *A Writer* - *Exclusive to Footballguys*

Some intro text that is not a pick and should be ignored.

Madeup Runner (RB-DEN)

*Bid Recommendation: 25-50% of Annual FAAB Budget*
He stepped in when the starter went down and looked explosive.
Worth a real bid if you need running back help.

Fictional Catcher (WR-NYJ)

*Bid Recommendation: 10-20% of Annual FAAB Budget*
Led the team in targets two weeks running.
"""

# The table-of-contents links. Real emails route through convertkit tracking
# links whose final path segment is base64 of the true footballguys URL. We fake
# that shape here so we can prove the decoder without shipping real links.
_REAL_URL = "https://www.footballguys.com/upgrades-and-downgrades"
_TRACKED = "https://ab12cd34.click.convertkit-mail.com/abc/xyz/" + (
    base64.b64encode(_REAL_URL.encode()).decode()
)
LINKS_SAMPLE = f"""In this issue:

    - Upgrades and Downgrades
    <{_TRACKED}>
    - Bloom breaks down who is trending up and who is trending down this week.
"""


def test_parse_extracts_each_pick_name_pos_team():
    picks = footballguys.parse_picks(FEATURE_SAMPLE)
    assert len(picks) == 2, f"expected 2 picks, got {len(picks)}"
    first = picks[0]
    assert first["name"] == "Madeup Runner", first["name"]
    assert first["pos"] == "RB", first["pos"]
    assert first["nfl_team"] == "DEN", first["nfl_team"]


def test_parse_captures_bid_recommendation():
    picks = footballguys.parse_picks(FEATURE_SAMPLE)
    assert picks[0]["bid_recommendation"] == "25-50% of Annual FAAB Budget", (
        picks[0]["bid_recommendation"]
    )


def test_parse_captures_multiline_reasoning():
    picks = footballguys.parse_picks(FEATURE_SAMPLE)
    reasoning = picks[0]["reasoning"]
    # Both reasoning sentences are joined into one string; the bid line is not
    # part of the reasoning.
    assert "explosive" in reasoning, reasoning
    assert "real bid" in reasoning, reasoning
    assert "Bid Recommendation" not in reasoning, reasoning


def test_parse_ignores_intro_prose():
    # A line like "By *A Writer*" is not "Name (POS-TEAM)" and must not become a
    # pick. Only lines whose position is a real fantasy position count.
    picks = footballguys.parse_picks(FEATURE_SAMPLE)
    names = {p["name"] for p in picks}
    assert names == {"Madeup Runner", "Fictional Catcher"}, names


def test_last_pick_reasoning_stops_before_links_section():
    # Regression: with no headline after it, the final pick used to swallow the
    # whole footer + link list. The inlined article ends where the links begin,
    # so the last pick's reasoning must not absorb the table of contents.
    picks = footballguys.parse_picks(FEATURE_SAMPLE + "\n" + LINKS_SAMPLE)
    last = picks[-1]
    assert "Upgrades and Downgrades" not in last["reasoning"], last["reasoning"]
    assert "targets two weeks running" in last["reasoning"], last["reasoning"]


def test_decode_tracking_url_recovers_real_footballguys_url():
    assert footballguys.decode_tracking_url(_TRACKED) == _REAL_URL


def test_decode_tracking_url_returns_none_for_undecodable():
    # A plain link with no base64 tail must not raise; it just can't be decoded.
    assert footballguys.decode_tracking_url("https://example.com/plain") is None


def test_parse_links_pairs_title_with_decoded_url():
    links = footballguys.parse_links(LINKS_SAMPLE)
    titles = {link["title"]: link for link in links}
    assert "Upgrades and Downgrades" in titles, titles
    assert titles["Upgrades and Downgrades"]["url"] == _REAL_URL


def test_parse_email_bundles_picks_and_links():
    parsed = footballguys.parse_email(
        FEATURE_SAMPLE + "\n" + LINKS_SAMPLE,
        subject="Sample Waiver Wire",
        received_date="2026-09-23",
    )
    assert parsed["subject"] == "Sample Waiver Wire"
    assert parsed["date"] == "2026-09-23"
    assert len(parsed["picks"]) == 2
    assert any(link["title"] == "Upgrades and Downgrades" for link in parsed["links"])


def test_store_daily_appends_and_dedupes_by_date():
    # Storage accumulates a week's worth of daily emails in one file, keyed by
    # date so re-processing the same day replaces rather than duplicates.
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        day1 = footballguys.parse_email(FEATURE_SAMPLE, received_date="2026-09-22")
        day2 = footballguys.parse_email(FEATURE_SAMPLE, received_date="2026-09-23")

        footballguys.store_daily(day1, season="2026", week=3, out_dir=out)
        footballguys.store_daily(day2, season="2026", week=3, out_dir=out)
        # Re-store day2: must replace, not add a third entry.
        footballguys.store_daily(day2, season="2026", week=3, out_dir=out)

        stored = footballguys.load_week(season="2026", week=3, out_dir=out)
        dates = [entry["date"] for entry in stored]
        assert dates == ["2026-09-22", "2026-09-23"], dates


# The same article as Gmail actually hands it back: the headline is underlined
# with dashes on the next line, and the bid line carries no asterisks. The
# first parser was written against a markdown-ish rendering and missed every
# bid in this form, and folded the underline into the reasoning.
PLAIN_SAMPLE = """Made Up Back (RB-DEN)
---------------------

Bid Recommendation: 25-50% of Annual FAAB Budget
He stepped in when the starter went down and looked explosive.

Pretend Receiver (WR-NYJ)
-------------------------

Bid Recommendation: 10-20% of Annual FAAB Budget
Led the team in targets two weeks running.

-->Check out the full Waiver Wire Report 👉 ( https://example.invalid/report )
Check out the full Waiver Wire Report 👉 ( https://example.invalid/report )
"""


def test_parse_reads_bid_without_asterisks_and_skips_underline():
    picks = footballguys.parse_picks(PLAIN_SAMPLE)
    assert [p["name"] for p in picks] == ["Made Up Back", "Pretend Receiver"], picks
    assert picks[0]["bid_recommendation"] == "25-50% of Annual FAAB Budget", picks[0]
    assert "---" not in picks[0]["reasoning"], picks[0]["reasoning"]
    assert "Bid Recommendation" not in picks[0]["reasoning"], picks[0]["reasoning"]


def test_last_pick_reasoning_stops_before_arrow_call_to_action():
    picks = footballguys.parse_picks(PLAIN_SAMPLE)
    assert "Check out" not in picks[-1]["reasoning"], picks[-1]["reasoning"]
    assert "targets two weeks running" in picks[-1]["reasoning"], picks[-1]["reasoning"]


# The "Upgrades, Downgrades, and Waiver Wire Wonders" email: one bullet per
# player under a "<Position> Upgrades" or "<Position> Downgrades" heading, with
# an optional "(waiver wire: X)" tail. A percentage on an upgrade is a bid; a
# "DROP FOR X OR HIGHER" on a downgrade says the player is cuttable.
PRIORITY_SAMPLE = """Running Back Upgrades
---------------------

* RB Made Up Back DEN (waiver wire: 10-20%)
* RB Already Owned Star BUF
* RB Cheap Flier Jr. SEA (waiver wire: 3-5%)

Running Back Downgrades
-----------------------

* RB Fading Vet WAS (waiver wire: DROP FOR 5-10% OR HIGHER)
* RB Hurt Starter NYJ

Wide Receiver Upgrades
----------------------

* WR Pretend Receiver NYJ (waiver wire: 15-30%)
"""


def test_parse_priority_list_extracts_adds_with_bids():
    rows = footballguys.parse_priority_list(PRIORITY_SAMPLE)
    adds = [r for r in rows if r["direction"] == "upgrade" and r["bid"]]
    assert [(r["name"], r["pos"], r["nfl_team"], r["bid"]) for r in adds] == [
        ("Made Up Back", "RB", "DEN", "10-20%"),
        ("Cheap Flier Jr.", "RB", "SEA", "3-5%"),
        ("Pretend Receiver", "WR", "NYJ", "15-30%"),
    ], adds


def test_parse_priority_list_keeps_upgrades_without_a_bid():
    rows = footballguys.parse_priority_list(PRIORITY_SAMPLE)
    owned = [r for r in rows if r["name"] == "Already Owned Star"][0]
    assert owned["direction"] == "upgrade" and owned["bid"] is None, owned


def test_parse_priority_list_marks_droppable_downgrades():
    rows = footballguys.parse_priority_list(PRIORITY_SAMPLE)
    vet = [r for r in rows if r["name"] == "Fading Vet"][0]
    assert vet["direction"] == "downgrade", vet
    assert vet["drop_for"] == "5-10%", vet
    hurt = [r for r in rows if r["name"] == "Hurt Starter"][0]
    assert hurt["direction"] == "downgrade" and hurt["drop_for"] is None, hurt


def run():
    test_parse_extracts_each_pick_name_pos_team()
    test_parse_captures_bid_recommendation()
    test_parse_captures_multiline_reasoning()
    test_parse_ignores_intro_prose()
    test_last_pick_reasoning_stops_before_links_section()
    test_decode_tracking_url_recovers_real_footballguys_url()
    test_decode_tracking_url_returns_none_for_undecodable()
    test_parse_links_pairs_title_with_decoded_url()
    test_parse_email_bundles_picks_and_links()
    test_store_daily_appends_and_dedupes_by_date()
    test_parse_reads_bid_without_asterisks_and_skips_underline()
    test_last_pick_reasoning_stops_before_arrow_call_to_action()
    test_parse_priority_list_extracts_adds_with_bids()
    test_parse_priority_list_keeps_upgrades_without_a_bid()
    test_parse_priority_list_marks_droppable_downgrades()
    print("footballguys tests passed")


if __name__ == "__main__":
    run()
