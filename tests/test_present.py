import pandas as pd
import pytest

import present
from chessstyle import fetch, profile


@pytest.mark.parametrize("z,step", [(0, 2), (0.149, 2), (0.15, 3), (0.449, 3), (0.45, 4), (-0.15, 1),
                                    (-0.449, 1), (-0.45, 0), (-2, 0), (float("nan"), None), (None, None)])
def test_scale_step(z, step):
    assert present.scale_step(z) == step


def test_every_feature_and_group_has_plain_words():
    assert set(present.PHRASES) == set(profile.FEATURES) == set(present.FEATURE_NAMES)
    assert set(present.LABELS) == set(profile.GROUPS) == set(present.GLYPHS)
    assert list(present.LABELS.values()) == ["Aggression", "King safety", "Simplifying", "Piece choices", "Clock use"]


def test_habit_sentence_reads_plainly():
    assert present.habit("time_mid", 0.86) == "You spend more of your clock in the middlegame than most players at your rating."
    assert present.habit("castle_move", -0.4) == "You castle earlier than most players at your rating."
    assert present.habit("game_len", 0.5).endswith("(your opponents affect this too)")


def test_trait_cards():
    vec = pd.Series(0.0, index=profile.FEATURES)
    vec[["time_mid", "time_trouble", "time_end"]] = [0.86, 0.77, -0.17]
    groups = pd.Series({g: vec[fs].mean() for g, fs in profile.GROUPS.items()})
    cards = present.trait_cards(groups, vec)
    assert [c["group"] for c in cards] == list(profile.GROUPS)
    clock = cards[-1]
    assert clock["label"] == "Clock use" and clock["step"] == 3 and clock["glyph"] == present.GLYPHS["Time use"]
    assert clock["summary"] == "A bit more than most players at your rating"
    assert len(clock["habits"]) == 3 and clock["habits"][0].startswith("You spend more of your clock in the middlegame")
    assert cards[0]["habits"] == [] and cards[0]["summary"] == "About typical for your rating"


def test_trait_card_with_no_data():
    vec = pd.Series(float("nan"), index=profile.FEATURES)
    groups = pd.Series({g: float("nan") for g in profile.GROUPS})
    card = present.trait_cards(groups, vec)[0]
    assert card["step"] is None and card["summary"] == "Not enough data" and card["habits"] == []


def test_match_words():
    assert present.match_words({"sim": 0.8, "lo": 0.734, "hi": 0.86, "p_top": 0.81}) == {
        "pct": "80% style match", "range": "likely 73–86%", "top3": "in the top 3 in 8 of 10 reshuffles of your games"}
    assert present.match_words({"sim": -0.2, "lo": -0.3, "hi": 0.1, "p_top": 0.0})["pct"] == "0% style match"


def test_shared_and_differs():
    vec = pd.Series({"time_mid": 0.9, "castled": 0.4, "checks": -0.3, "pawn_storm": -0.5})
    assert present.shared_sentence(["time_mid", "checks"], vec) == \
        "you both spend more of your clock in the middlegame and give fewer checks"
    assert present.shared_sentence(["time_mid", "castled", "checks"], vec) == (
        "you both spend more of your clock in the middlegame, castle in more of your games and give fewer checks")
    assert present.shared_sentence([], vec) == ""
    assert present.differs_sentence("pawn_storm", vec) == \
        "you push pawns at the enemy king less often; they tend the other way"
    assert present.differs_sentence(None, vec) == ""


def test_blunder_words():
    assert present.blunder_words(0.59, 0.51) == "a bit more often than"
    assert present.blunder_words(0.5, 0.5) == "about as often as"
    assert present.blunder_words(0.2, 0.5) == "much less often than"
    assert present.blunder_words(float("nan"), 0.5) == "not available"


def test_openings_and_boards():
    fams = set(pd.read_csv(fetch.DATA / "gm_games.csv").family)
    assert fams <= set(present.OPENINGS)
    assert present.opening_name("french") == "French Defence"
    assert present.opening_name("made-up") == "made-up"
    assert present.board_uri("french", "black").startswith("data:image/svg+xml;base64,")
    assert present.board_uri("other", "white") is None


def test_flag():
    assert present.flag("IN") == "🇮🇳"
    assert present.flag("") == "" and present.flag("XXX") == "" and present.flag("12") == ""
