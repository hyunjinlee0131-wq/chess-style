import numpy as np
import pandas as pd
import pytest

from chessstyle import match, profile

F = profile.FEATURES


def profiles():
    """Three GMs defined only on the first 4 features; the rest are NaN."""
    return pd.DataFrame([[2, 1, 0, -1], [2, 1, 0, 1], [-2, -1, 0, 1]],
                        index=["a", "b", "c"], columns=F[:4], dtype=float).reindex(columns=F)


def test_self_is_top_match_and_nan_dims_ignored():
    P = profiles()
    s = match.similarities(P.loc["a"], P)
    assert s["a"] == pytest.approx(1) and s.idxmax() == "a" and s.notna().all()


def test_explain_shared_and_differs():
    P = profiles()
    e = match.explain(P.loc["a"], P.loc["b"])
    assert e == {"shared": [F[0], F[1], F[2]], "differs": F[3]}


def test_bootstrap_identical_player_always_top():
    P = profiles()
    b = match.bootstrap(pd.DataFrame([P.loc["a"]] * 30), P, n=50)
    assert b.index[0] == "a" and b.loc["a", "p_top"] == 1


def gm_table(n_gm=6, n_games=240, noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(n_gm, len(F)))
    rows = [{"username": f"gm{g}", "end_time": i, "side": ("white", "black")[i % 2], "family": "open",
             "game": f"g{g}-{i}", **dict(zip(F, centres[g] + noise * rng.normal(size=len(F))))}
            for g in range(n_gm) for i in range(n_games)]
    return pd.DataFrame(rows)


def test_identify_finds_distinct_gms_and_shuffle_is_near_chance():
    t = gm_table()
    assert match.identify(t, chunk=25)["top1"] > 0.9
    assert match.identify(t, chunk=25, shuffle=True)["top1"] < 0.5


def test_reading_list_filters_gm_and_opening_newest_first():
    t = gm_table(n_gm=2, n_games=6)
    assert match.reading_list(t, "gm0", ["open|white"], n=2) == ["g0-4", "g0-2"]
