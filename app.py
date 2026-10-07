"""Which grandmaster plays like me? Streamlit page. Run: streamlit run app.py"""
import urllib.error

import pandas as pd
import streamlit as st

from chessstyle import features, fetch, match, profile

N_GAMES = 300
REPO = "https://github.com/hyunjinlee0131-wq/chess-style"


@st.cache_resource
def gm_profiles():
    gm = pd.read_csv(fetch.DATA / "gm_games.csv")
    return gm, profile.vectors(profile.normalise(gm, gm.username.notna()))


def report(table, gm, P):
    """Features table -> everything the page shows. ValueError if there are too few games."""
    if table.empty or not (table.who == "player").any():
        raise ValueError("no rated rapid games with 10+ moves found")
    z, cur = profile.player_frame(table)
    me, mine = z[cur], table[cur]
    vec = me[profile.FEATURES].mean()
    peers = table[table.game.isin(mine.game) & (table.who == "opponent")]
    boot = match.bootstrap(me, P).head(5)
    fams = (mine.family + "|" + mine.side).value_counts().head(3).index
    return {
        "games": int(cur.sum()),
        "ratings": (int(me.rating.min()), int(me.rating.max())),
        "groups": pd.Series({g: vec[fs].mean() for g, fs in profile.GROUPS.items()}),
        "features": vec,
        "openings": (mine.family + " as " + mine.side).value_counts(normalize=True).head(6),
        "blunders": (mine.material_blunders.mean(), peers.material_blunders.mean()),
        "matches": [{"user": u, **r.to_dict(), **match.explain(vec, P.loc[u])} for u, r in boot.iterrows()],
        "reading": match.reading_list(gm, boot.index[0], fams),
    }
