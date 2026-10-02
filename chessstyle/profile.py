"""Rating bands, opening adjustment and peer z-scores -> style vectors."""
import numpy as np
import pandas as pd

GROUPS = {
    "Aggression": ["checks", "captures", "sacrifices", "early_queen"],
    "King play": ["castled", "castle_move", "castle_long", "opposite_castle", "pawn_storm"],
    "Simplification": ["queen_trade", "queen_trade_move", "material_30", "endgame", "game_len"],
    "Piece preference": ["bishop_takes_knight", "bishop_pair_kept", "pawn_share"],
    "Time use": ["time_open", "time_mid", "time_end", "time_trouble"],
}
FEATURES = [f for fs in GROUPS.values() for f in fs]
# Both players shape these, so the opponent baseline partly shares them (spec §2 known bias).
INTERACTIVE = {"opposite_castle", "queen_trade", "queen_trade_move", "material_30", "endgame", "game_len"}


def assign_bands(df, n=5, min_rating=1000, min_per_band=100):
    """Equal-count bands over the player's games rated >= min_rating; opponents share their game's band."""
    ok = df.player_rating >= min_rating
    ratings = df.player_rating[ok & (df.who == "player")]
    n = min(n, len(ratings) // min_per_band)
    if n < 1:
        raise ValueError(f"need at least {min_per_band} rated rapid games at {min_rating}+ (found {len(ratings)})")
    _, edges = pd.qcut(ratings, n, retbins=True, duplicates="drop")
    return df.assign(band=pd.cut(df.player_rating.where(ok), edges, labels=False, include_lowest=True))


def current_mask(df, window=150, min_games=200):
    """Player rows within `window` of the latest rating (widened to 250 if fewer than `min_games`)."""
    p = df[df.who == "player"]
    latest = p.sort_values("end_time").rating.iloc[-1]
    cut = latest - window
    if (p.rating >= cut).sum() < min_games:
        cut = latest - 250
    return (df.who == "player") & (df.rating >= cut)


def normalise(df, ref, group=None, min_family=20, by_opening=True):
    """Opening-adjust, then z-score FEATURES against reference rows `ref` (bool Series) within `group`."""
    df = df.copy()
    ref = ref.reindex(df.index, fill_value=False)
    key = group or "_g"
    if group is None:
        df[key] = 0
    df["fam"] = df.family + "|" + df.side
    if by_opening:
        n = df[ref].groupby([key, "fam"]).size()
        ok = pd.MultiIndex.from_frame(df[[key, "fam"]]).isin(n[n >= min_family].index)
        df["fam"] = df.fam.where(ok, "other|" + df.side)
        mu = df[ref].groupby([key, "fam"])[FEATURES].mean()
        df[FEATURES] = df[FEATURES].to_numpy() - mu.reindex(pd.MultiIndex.from_frame(df[[key, "fam"]])).to_numpy()
    stats = df[ref].groupby(key)[FEATURES]
    mean, sd = stats.mean(), stats.std().replace(0, np.nan)
    df[FEATURES] = (df[FEATURES].to_numpy() - mean.reindex(df[key]).to_numpy()) / sd.reindex(df[key]).to_numpy()
    return df.drop(columns="_g", errors="ignore")


def player_frame(table):
    """Bands + normalisation against same-band opponents. Returns (z-scored rows, current-games mask)."""
    df = assign_bands(table)
    z = normalise(df, (df.who == "opponent") & df.band.notna(), group="band")
    return z, current_mask(z) & z.band.notna()


def vectors(z):
    return z.groupby("username")[FEATURES].mean()
