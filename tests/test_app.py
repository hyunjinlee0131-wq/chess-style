import pandas as pd
import pytest

import app
from chessstyle import fetch, profile


def fake_table():
    """One GM's games as 'player' vs another GM's rows as 'opponent': real feature values, valid shape."""
    gm = pd.read_csv(fetch.DATA / "gm_games.csv")
    a, b = gm.username.value_counts().index[:2]
    p = gm[gm.username == a].head(300).assign(who="player")
    p = p.assign(player_rating=p.rating)
    o = gm[gm.username == b].head(len(p)).assign(
        who="opponent", game=p.game.values, end_time=p.end_time.values, player_rating=p.rating.values)
    return pd.concat([p, o], ignore_index=True).drop(columns="pool")


def test_report_has_everything_the_page_shows():
    gm, P, info = app.gm_profiles()
    r = app.report(fake_table(), gm, P, info)
    assert set(r) == {"games", "ratings", "groups", "features", "raw", "peer_raw", "openings", "blunders",
                      "matches", "reading"}
    assert list(r["groups"].index) == list(profile.GROUPS)
    assert len(r["matches"]) == 4
    assert [m["sim"] for m in r["matches"]] == sorted((m["sim"] for m in r["matches"]), reverse=True)
    m = r["matches"][0]
    assert {"user", "sim", "lo", "hi", "p_top", "shared", "differs", "gm_features", "name", "title", "avatar", "country",
            "openings"} <= set(m)
    assert m["name"] and m["openings"] and set(m["openings"][0]) == {"family", "side", "share"}
    assert 1 <= len(r["openings"]) <= 3 and set(r["openings"][0]) == {"family", "side", "share"}
    assert set(r["raw"].index) == set(profile.FEATURES)
    assert r["reading"] and set(r["reading"][0]) == {"url", "date", "family", "side", "opponent", "result"}
    assert all(x["url"].startswith("https://") and len(x["date"]) == 10 for x in r["reading"])
    assert {x["result"] for x in r["reading"]} <= {"win", "loss", "draw", ""}


def test_report_empty_table_is_a_clear_error():
    gm, P, info = app.gm_profiles()
    with pytest.raises(ValueError, match="no rated rapid games"):
        app.report(pd.DataFrame(), gm, P, info)


def test_gm_without_profile_falls_back_to_username():
    gm, P, info = app.gm_profiles()
    m = app.report(fake_table(), gm, P, info.iloc[0:0])["matches"][0]
    assert m["name"] == m["user"] and m["avatar"] == "" and m["title"] == ""


def test_reading_rows_empty_when_no_games_in_openings():
    gm, _, _ = app.gm_profiles()
    assert app.reading_rows(gm, gm.username.iloc[0], ["no-such-family|white"]) == []


def test_gm_results_are_merged():
    gm, _, _ = app.gm_profiles()
    assert {"opponent", "result"} <= set(gm.columns)
    assert gm.result.notna().mean() > 0.95
