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
    gm, P = app.gm_profiles()
    r = app.report(fake_table(), gm, P)
    assert set(r) == {"games", "ratings", "groups", "features", "openings", "blunders", "matches", "reading"}
    assert list(r["groups"].index) == list(profile.GROUPS)
    assert len(r["matches"]) == 5
    assert [m["sim"] for m in r["matches"]] == sorted((m["sim"] for m in r["matches"]), reverse=True)
    assert {"user", "sim", "lo", "hi", "p_top", "shared", "differs"} <= set(r["matches"][0])
    assert all(u.startswith("https://") for u in r["reading"])


def test_report_empty_table_is_a_clear_error():
    gm, P = app.gm_profiles()
    with pytest.raises(ValueError, match="no rated rapid games"):
        app.report(pd.DataFrame(), gm, P)
