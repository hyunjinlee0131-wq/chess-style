"""Cosine style matching, bootstrap uncertainty, reading list and GM identification test."""
import warnings

import numpy as np
import pandas as pd

from chessstyle.profile import FEATURES, normalise


def similarities(vec, profiles):
    """Cosine similarity of `vec` to each profile row, using only dimensions both have."""
    A = profiles.to_numpy(dtype=float)
    v = vec.reindex(profiles.columns).to_numpy(dtype=float)
    m = ~np.isnan(A) & ~np.isnan(v)
    a, b = np.where(m, A, 0), np.where(m, v, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = (a * b).sum(1) / np.sqrt((a * a).sum(1) * (b * b).sum(1))
    return pd.Series(s, index=profiles.index)


def explain(vec, gm_vec, k=3):
    """Top-k features pulling the two styles together, and the one pulling hardest apart (if any)."""
    c = (vec * gm_vec).dropna().sort_values(ascending=False)
    return {"shared": list(c.index[:k]), "differs": c.index[-1] if c.iloc[-1] < 0 else None}


def bootstrap(rows, profiles, n=1000, top=3, seed=0):
    """Resample the player's z-scored game rows -> similarity mean, 95% interval, P(GM in top `top`)."""
    rng = np.random.default_rng(seed)
    X = rows[FEATURES].to_numpy(dtype=float)
    sims = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN feature columns
        for _ in range(n):
            v = pd.Series(np.nanmean(X[rng.integers(0, len(X), len(X))], axis=0), index=FEATURES)
            sims.append(similarities(v, profiles))
    S = pd.DataFrame(sims)
    in_top = S.rank(axis=1, ascending=False) <= top
    return pd.DataFrame({"sim": S.mean(), "lo": S.quantile(0.025), "hi": S.quantile(0.975),
                         "p_top": in_top.mean()}).sort_values("sim", ascending=False)


def reading_list(gm_games, gm, fams, n=10):
    """Newest games by `gm` in the player's opening keys ('family|side')."""
    g = gm_games[(gm_games.username == gm) & (gm_games.family + "|" + gm_games.side).isin(fams)]
    return g.sort_values("end_time", ascending=False).game.head(n).tolist()


def identify(gm_games, chunk=100, train_frac=0.5, by_opening=True, shuffle=False, drop=None, seed=0):
    """Profile each GM from their earliest games; can chunks of their later games be matched back to them?"""
    rng = np.random.default_rng(seed)
    t = gm_games.sort_values("end_time", kind="stable").reset_index(drop=True)
    if shuffle:
        t["username"] = rng.permutation(t.username.to_numpy())
    pos = t.groupby("username").cumcount()
    train = pos < train_frac * t.groupby("username").username.transform("size")
    z = normalise(t, train, by_opening=by_opening)
    if drop:
        z.loc[~train, drop] = rng.permutation(z.loc[~train, drop].to_numpy())
    X = z[FEATURES]
    profiles = X[train].groupby(z.username[train]).mean()
    ranks = []
    for gm, rows in X[~train].groupby(z.username[~train]):
        for s in range(0, len(rows) - chunk + 1, chunk):
            ranks.append(similarities(rows.iloc[s:s + chunk].mean(), profiles).rank(ascending=False)[gm])
    ranks = pd.Series(ranks, dtype=float)
    k = len(profiles)
    return {"top1": (ranks <= 1).mean(), "top5": (ranks <= 5).mean(), "chance_top5": min(5, k) / k, "tests": len(ranks)}
