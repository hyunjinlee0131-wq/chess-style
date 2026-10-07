"""Which grandmaster plays like me? Streamlit page. Run: streamlit run app.py"""
import urllib.error
from pathlib import Path

import pandas as pd
import streamlit as st

import present
from chessstyle import features, fetch, match, profile

N_GAMES = 300
EXAMPLE = "ssgssg2"


POOLS = {"rapid": ("gm_games.csv", "gm_results.csv"), "blitz": ("gm_blitz.csv", "gm_blitz_results.csv")}


@st.cache_resource
def gm_profiles(time_class="rapid"):
    """GM games (with opponent and result), GM style vectors, GM profile details — for one time control."""
    games, results = POOLS[time_class]
    gm = pd.read_csv(fetch.DATA / games).merge(
        pd.read_csv(fetch.DATA / results, keep_default_na=False), on=["game", "username"], how="left")
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
            "gm_features": P.loc[u].to_dict(), "name": d.get("name") or u, "title": d.get("title", ""), "avatar": d.get("avatar", ""),
            "country": d.get("country", ""), "openings": top_openings(gm[gm.username == u])}


def report(table, gm, P, info, time_class="rapid"):
    """Features table -> everything the page shows. ValueError if there are too few games."""
    if table.empty or not (table.who == "player").any():
        raise ValueError(f"no rated {time_class} games with 10+ moves found")
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
        "quality": present.quality_rows(mine, peers),
        "matches": [gm_card(u, r, vec, P, gm, info) for u, r in boot.iterrows()],
        "reading": reading_rows(gm, boot.index[0], fams),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def analyse(username, time_class="rapid"):
    games = fetch.games(username, time_class, limit=N_GAMES)
    engine = features.open_engine()
    try:
        table = features.features_table(games, username, engine)
    finally:
        if engine:
            engine.quit()
    gm, P, info = gm_profiles(time_class)
    return report(table, gm, P, info, time_class)


if st.runtime.exists():
    st.set_page_config(page_title="Which GM plays like you?", page_icon="♞", layout="centered")
    st.markdown(f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True)
    n_gms = len(gm_profiles("rapid")[1])
    st.markdown(
        '<div class="cs-hero"><div class="glyph">♞</div><h1>Which grandmaster plays like you?</h1>'
        f"<p>We read your last {N_GAMES} rated rapid or blitz games on chess.com, compare your habits with players at your "
        f"rating, and find which of {n_gms} grandmasters and chess personalities play most like you.</p></div>",
        unsafe_allow_html=True)

    with st.form("lookup"):
        username = st.text_input("Your chess.com username", placeholder="e.g. hikaru").strip().lower()
        options = [tc.capitalize() for tc in POOLS]
        picked = st.segmented_control("Time control", options, default="Rapid") if len(options) > 1 else "Rapid"
        time_class = (picked or "Rapid").lower()
        left, right = st.columns(2)
        go = left.form_submit_button("Find my grandmaster", type="primary", width="stretch")
        example = right.form_submit_button(f"Try an example ({EXAMPLE})", width="stretch")
    if example:
        username, go = EXAMPLE, True
    if not (go and username):
        st.stop()

    try:
        with st.spinner(f"Reading {username}'s recent {time_class} games and comparing habits... (about 20 seconds)"):
            r = analyse(username, time_class)
    except ValueError as e:
        st.error(str(e))
        st.stop()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        st.error("chess.com didn't respond. Try again in a minute.")
        st.stop()

    html = lambda s: st.markdown(s, unsafe_allow_html=True)
    vec = r["features"]
    cards = present.trait_cards(r["groups"], vec)

    html(present.section_html("♚", "Your style", "compared with players at your rating"))
    left, right = st.columns([2, 3])
    left.pyplot(present.radar(cards), width="stretch")
    with right:
        for c in cards:
            html(present.trait_card_html(c))

    html(present.section_html("♔", "How well you play", f"compared with players at your rating, in {time_class}"))
    for col, q in zip(st.columns(3), r["quality"]):
        with col:
            html(present.quality_card_html(q))

    html(present.section_html("♟", "Your openings", "your most played"))
    for col, o in zip(st.columns(3), r["openings"]):
        with col:
            html(present.opening_html(o))

    html(present.section_html("♛", "Your closest players", "grandmasters and chess personalities"))
    top, *rest = r["matches"]
    html(present.gm_hero_html(top, vec))
    used = set()
    for rank, (col, m) in enumerate(zip(st.columns(3), rest), start=2):
        shared = present.shared_features(vec, m["gm_features"])
        feature = next((f for f in shared if f not in used), shared[0] if shared else None)
        used.add(feature)
        with col:
            html(present.gm_small_html(m, vec, rank, feature))

    if r["reading"]:
        html(present.section_html("♗", f"Study {top['name']}'s games", "in the openings you play"))
        html(present.reading_table_html(r["reading"]))

    with st.expander("Show the numbers"):
        st.caption("Your average per game next to players at your rating. 'Compared with them' also allows for the "
                   "openings you play, so it can differ slightly from the raw averages.")
        st.dataframe(present.numbers_table(r), hide_index=True, width="stretch")
    with st.expander("How does this work?"):
        steps = [
            f"Each of your games becomes {len(profile.FEATURES)} habits: how often you check and capture, when you castle, "
            f"when queens come off, how you spend your clock, and so on.",
            "Those habits are compared with your opponents at the same rating, allowing for the openings you "
            "play, so the result describes style rather than strength or repertoire.",
            f"The same is done for {n_gms} grandmasters and chess personalities; the closest ones share the most "
            f"habits with you.",
            "To show how sure the match is, your games are reshuffled and re-checked 1,000 times. "
            "The 'likely between' range and 'stays in your top 3' come from that.",
        ]
        if len(POOLS) > 1:
            steps.insert(0, "Pick Rapid or Blitz: your games are only compared with grandmaster games of the same "
                            "speed, because time pressure changes habits.")
        st.markdown(
            "\n".join(f"{i}. {t}" for i, t in enumerate(steps, 1)) + "\n\n"
            "Tested on grandmasters themselves: given 100 of a grandmaster's games, the method puts the right one in "
            "its top 5 44% of the time (picking at random would manage 10%).\n\n"
            "**How well you play** compares your accuracy (from chess.com game review), material blunders and time "
            "trouble with your opponents in the same games: Bad, Weak, Average, Good or Excellent for your rating. "
            "Your style, above, is never rated good or bad — it only says how distinctive it is.")

    html(f'<p class="cs-muted" style="text-align:center;margin-top:2rem">Based on {r["games"]} recent {time_class} games, '
         f'rating {r["ratings"][0]}–{r["ratings"][1]}.</p>')
