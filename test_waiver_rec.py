"""
Tests for the waiver recommendation facts: matching footballguys' advice to
what is actually available in the league, and sizing bids to Dan's budget.

Same style as the other tests: plain asserts, stdlib only, run with
    python3 test_waiver_rec.py

Fixtures use INVENTED players. Footballguys content never lives in a test.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import waiver_rec  # noqa: E402  (import after sys.path setup, like the other tests)


FREE_AGENTS = [
    {"player_id": "1", "name": "Made Up Back", "pos": "RB", "nfl_team": "DEN", "injury": None},
    {"player_id": "2", "name": "Pretend Receiver", "pos": "WR", "nfl_team": "NYJ", "injury": None},
    {"player_id": "3", "name": "Cheap Flier", "pos": "RB", "nfl_team": "SEA", "injury": "Questionable"},
]
# Dan's roster: one player footballguys says to add (already his), one they
# say is cuttable, and one nobody mentioned.
MY_ROSTER = [
    {"player_id": "10", "name": "Already Owned Star", "pos": "RB", "nfl_team": "BUF"},
    {"player_id": "11", "name": "Fading Vet", "pos": "RB", "nfl_team": "WAS"},
    {"player_id": "12", "name": "Quiet Tight End", "pos": "TE", "nfl_team": "KC"},
]
PICKS = [
    {"name": "Made Up Back", "pos": "RB", "nfl_team": "DEN",
     "bid_recommendation": "25-50% of Annual FAAB Budget", "reasoning": "Explosive."},
    {"name": "Taken Elsewhere", "pos": "WR", "nfl_team": "MIA",
     "bid_recommendation": "10-20% of Annual FAAB Budget", "reasoning": "Owned by a rival."},
]
PRIORITY = [
    {"name": "Cheap Flier Jr.", "pos": "RB", "nfl_team": "SEA", "direction": "upgrade", "bid": "3-5%", "drop_for": None},
    {"name": "Already Owned Star", "pos": "RB", "nfl_team": "BUF", "direction": "upgrade", "bid": None, "drop_for": None},
    {"name": "Fading Vet", "pos": "RB", "nfl_team": "WAS", "direction": "downgrade", "bid": None, "drop_for": "5-10%"},
    {"name": "Pretend Receiver", "pos": "WR", "nfl_team": "NYJ", "direction": "upgrade", "bid": "15-30%", "drop_for": None},
]


def test_normalize_name_ignores_suffix_punctuation_and_case():
    assert waiver_rec.normalize_name("Cheap Flier Jr.") == waiver_rec.normalize_name("cheap flier")
    assert waiver_rec.normalize_name("Ollie Gordon II") == waiver_rec.normalize_name("Ollie Gordon")
    assert waiver_rec.normalize_name("De'Von Achane") == waiver_rec.normalize_name("DeVon Achane")


def test_available_adds_are_only_recommended_players_in_the_free_pool():
    facts = waiver_rec.match_advice(PICKS, PRIORITY, FREE_AGENTS, MY_ROSTER)
    names = [a["name"] for a in facts["available"]]
    assert "Made Up Back" in names, names
    assert "Pretend Receiver" in names, names
    assert "Cheap Flier" in names, names  # matched despite the "Jr." in the advice
    assert "Taken Elsewhere" not in names, names


def test_featured_pick_reasoning_and_bid_travel_with_the_match():
    facts = waiver_rec.match_advice(PICKS, PRIORITY, FREE_AGENTS, MY_ROSTER)
    back = [a for a in facts["available"] if a["name"] == "Made Up Back"][0]
    assert back["bid_pct"] == "25-50%", back
    assert back["reasoning"] == "Explosive.", back
    assert back["player_id"] == "1", back  # the Sleeper id, so the add is unambiguous


def test_recommended_players_owned_by_others_are_listed_as_gone():
    facts = waiver_rec.match_advice(PICKS, PRIORITY, FREE_AGENTS, MY_ROSTER)
    assert [g["name"] for g in facts["gone"]] == ["Taken Elsewhere"], facts["gone"]


def test_my_droppable_players_come_from_downgrades_with_a_drop_figure():
    facts = waiver_rec.match_advice(PICKS, PRIORITY, FREE_AGENTS, MY_ROSTER)
    assert [d["name"] for d in facts["droppable"]] == ["Fading Vet"], facts["droppable"]
    assert facts["droppable"][0]["drop_for"] == "5-10%"


def test_my_players_footballguys_likes_are_flagged_as_hold():
    facts = waiver_rec.match_advice(PICKS, PRIORITY, FREE_AGENTS, MY_ROSTER)
    assert [h["name"] for h in facts["hold"]] == ["Already Owned Star"], facts["hold"]


def test_bid_range_scales_percent_of_budget_to_dollars():
    # 10-20% of a $100 budget is $10-$20, regardless of what is left.
    assert waiver_rec.bid_dollars("10-20%", budget=100) == (10, 20)
    assert waiver_rec.bid_dollars("25-50% of Annual FAAB Budget", budget=100) == (25, 50)
    assert waiver_rec.bid_dollars("0-1%", budget=100) == (0, 1)


def test_bid_range_returns_none_for_unparseable_text():
    assert waiver_rec.bid_dollars(None, budget=100) is None
    assert waiver_rec.bid_dollars("priority add", budget=100) is None


def test_bid_is_capped_at_remaining_budget():
    assert waiver_rec.bid_dollars("25-50%", budget=100, remaining=30) == (25, 30)
    assert waiver_rec.bid_dollars("40-60%", budget=100, remaining=30) == (30, 30)


def run():
    test_normalize_name_ignores_suffix_punctuation_and_case()
    test_available_adds_are_only_recommended_players_in_the_free_pool()
    test_featured_pick_reasoning_and_bid_travel_with_the_match()
    test_recommended_players_owned_by_others_are_listed_as_gone()
    test_my_droppable_players_come_from_downgrades_with_a_drop_figure()
    test_my_players_footballguys_likes_are_flagged_as_hold()
    test_bid_range_scales_percent_of_budget_to_dollars()
    test_bid_range_returns_none_for_unparseable_text()
    test_bid_is_capped_at_remaining_budget()
    print("waiver_rec tests passed")


if __name__ == "__main__":
    run()
