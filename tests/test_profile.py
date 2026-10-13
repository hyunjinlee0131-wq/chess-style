import numpy as np
import pandas as pd
import pytest

from chessstyle import profile

F = profile.FEATURES


def table(n_games, rating_of, seed=0):
    """Synthetic features table: player alternates colours, two opening families."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_games):
        r = rating_of(i)
        family = ("french", "sicilian")[i % 4 // 2]
        me = "white" if i % 2 == 0 else "black"
        for who, side in (("player", me), ("opponent", "black" if me == "white" else "white")):
            rows.append({"game": i, "end_time": i, "who": who, "side": side, "rating": r, "player_rating": r,
                         "username": who, "family": family, **dict(zip(F, rng.normal(size=len(F))))})
    return pd.DataFrame(rows)


def test_normalise_centres_families_and_scales():
    df = profile.assign_bands(table(800, lambda i: 1000 + i))
    ref = df.who == "opponent"
    r = profile.normalise(df, ref, group="band", min_family=5)[ref]
    assert np.allclose(r.groupby(["band", "fam"])[F].mean(), 0, atol=1e-9)
    assert np.allclose(r.groupby("band")[F].std(), 1)


def test_bands_equal_count_and_below_1000_excluded():
    df = profile.assign_bands(table(700, lambda i: 500 + 2 * i))
    p = df[df.who == "player"]
    assert p[p.player_rating < 1000].band.isna().all()
    counts = p.band.value_counts()
    assert len(counts) == 4 and counts.max() - counts.min() <= 1


def test_too_few_games_is_a_clear_error():
    with pytest.raises(ValueError, match="at least 100"):
        profile.assign_bands(table(150, lambda i: 600))


def test_current_window_widens_when_too_few_games():
    df = table(400, lambda i: 1000 + 2 * i)  # latest 1798; only 76 games >= 1648 -> widen to 1548
    m = profile.current_mask(df)
    assert (df[m].who == "player").all() and df[m].rating.min() == 1548


def test_constant_feature_gives_nan_not_inf():
    df = profile.assign_bands(table(800, lambda i: 1000 + i))
    df["castled"] = 1.0
    z = profile.normalise(df, df.who == "opponent", group="band", min_family=5)
    assert z.castled.isna().all()
