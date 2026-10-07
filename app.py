"""Which grandmaster plays like me? Streamlit page. Run: streamlit run app.py"""
import urllib.error

import pandas as pd
import streamlit as st

from chessstyle import features, fetch, match, profile

N_GAMES = 300
REPO = "https://github.com/hyunjinlee0131-wq/chess-style"


@st.cache_resource
def gm_profiles():
    """GM games (with opponent and result), GM style vectors, GM profile details indexed by username."""
    gm = pd.read_csv(fetch.DATA / "gm_games.csv").merge(
        pd.read_csv(fetch.DATA / "gm_results.csv", keep_default_na=False), on=["game", "username"], how="left")
    info = pd.read_csv(fetch.DATA / "gm_info.csv", keep_default_na=False).set_index("username")
    return gm, profile.vectors(profile.normalise(gm, gm.username.notna())), info


def top_openings(rows, n=3):
    s = (rows.family + "|" + rows.side).value_counts(normalize=True).head(n)
    return [{"family": k.split("|")[0], "side": k.split("|")[1], "share": float(v)} for k, v in s.items()]


def reading_rows(gm, user, fams):
    """The GM's newest games in the player's openings, as table rows."""
    urls = match.reading_list(gm, user, fams)
    g = gm[(gm.username == user) & gm.game.isin(urls)].drop_duplicates("game").set_index("game")
    text = lambda x: x if isinstance(x, str) else ""
    return [{"url": u, "date": pd.to_datetime(g.at[u, "end_time"], unit="s").strftime("%Y-%m-%d"),
             "family": g.at[u, "family"], "side": g.at[u, "side"],
             "opponent": text(g.at[u, "opponent"]), "result": text(g.at[u, "result"])} for u in urls]


def gm_card(u, r, vec, P, gm, info):
    d = info.loc[u].to_dict() if u in info.index else {}
    return {"user": u, **r.to_dict(), **match.explain(vec, P.loc[u]),
            "name": d.get("name") or u, "title": d.get("title", ""), "avatar": d.get("avatar", ""),
            "country": d.get("country", ""), "openings": top_openings(gm[gm.username == u])}


def report(table, gm, P, info):
    """Features table -> everything the page shows. ValueError if there are too few games."""
    if table.empty or not (table.who == "player").any():
        raise ValueError("no rated rapid games with 10+ moves found")
    z, cur = profile.player_frame(table)
    me, mine = z[cur], table[cur]
    vec = me[profile.FEATURES].mean()
    peers = table[table.game.isin(mine.game) & (table.who == "opponent")]
    boot = match.bootstrap(me, P).head(4)
    fams = (mine.family + "|" + mine.side).value_counts().head(3).index
    return {
        "games": int(cur.sum()),
        "ratings": (int(me.rating.min()), int(me.rating.max())),
        "groups": pd.Series({g: vec[fs].mean() for g, fs in profile.GROUPS.items()}),
        "features": vec,
        "raw": mine[profile.FEATURES].mean(),
        "peer_raw": peers[profile.FEATURES].mean(),
        "openings": top_openings(mine),
        "blunders": (mine.material_blunders.mean(), peers.material_blunders.mean()),
        "matches": [gm_card(u, r, vec, P, gm, info) for u, r in boot.iterrows()],
        "reading": reading_rows(gm, boot.index[0], fams),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def analyse(username):
    games = fetch.games(username, limit=N_GAMES)
    engine = features.open_engine()
    try:
        table = features.features_table(games, username, engine)
    finally:
        if engine:
            engine.quit()
    gm, P, info = gm_profiles()
    return report(table, gm, P, info)


if st.runtime.exists():
    st.set_page_config(page_title="Which GM plays like me?", page_icon="♟")
    st.title("Which grandmaster plays like me?")
    gm, P, info = gm_profiles()
    st.caption(f"Your style from your last {N_GAMES} rated rapid games on chess.com, measured against players at "
               f"your rating and adjusted for openings, then matched to {len(P)} GMs. "
               f"[Method and validation]({REPO})")

    with st.form("lookup"):
        username = st.text_input("chess.com username").strip().lower()
        go = st.form_submit_button("Analyse")
    if not (go and username):
        st.stop()

    try:
        with st.spinner(f"Downloading and analysing {username}'s recent games..."):
            r = analyse(username)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        st.error("chess.com didn't respond. Try again in a minute.")
        st.stop()

    st.subheader("Style profile")
    st.caption("σ = standard deviations from players at your rating; 0 = typical.")
    st.bar_chart(r["groups"], horizontal=True)
    rows = [(g, f, "unavailable" if pd.isna(r["features"][f]) else round(r["features"][f], 2), "both players shape this" if f in profile.INTERACTIVE else "")
            for g, fs in profile.GROUPS.items() for f in fs]
    st.dataframe(pd.DataFrame(rows, columns=["group", "feature", "σ", "note"]), hide_index=True)

    st.subheader("Openings")
    left, right = st.columns(2)
    left.dataframe(pd.DataFrame(r["openings"]))
    you, peers = r["blunders"]
    if pd.isna(you):
        right.metric("Material blunders / game", "unavailable")
    else:
        right.metric("Material blunders / game", f"{you:.2f}", f"{you - peers:+.2f} vs peers", delta_color="inverse")

    st.subheader("Closest grandmasters")
    for m in r["matches"]:
        st.markdown(f"**{m['user']}** — similarity {m['sim']:.2f} (95% interval {m['lo']:.2f}–{m['hi']:.2f}), "
                    f"top-3 in {m['p_top']:.0%} of resamples  \n"
                    f"shared: {', '.join(m['shared'])} · differs most: {m['differs']}")

    st.subheader(f"Reading list: {r['matches'][0]['user']} in your openings")
    for x in r["reading"]:
        st.markdown(f"- {x['date']} · {x['result']} · {x['url']}")

    st.caption(f"Based on {r['games']} current games, rating {r['ratings'][0]}–{r['ratings'][1]}.")
