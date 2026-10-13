"""One-off: build a pool of ~50 well-known / top-ranked GMs (+ a few famous media players) and save their per-game rapid features
to data/gm_games.csv. Famous names first (verified via the API), then the chess.com rapid/blitz
leaderboards' GMs by rapid rating. Downloads every monthly archive per GM; resumable via the cache."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd

from chessstyle import features, fetch

# Top players and YouTube/stream personalities. `chessbrah` left out: a shared multi-person account.
FAMOUS = ["magnuscarlsen", "hikaru", "fabianocaruana", "lachesisq", "firouzja2003", "lyonbeast",
          "levonaronian", "gmwso", "anishgiri", "chesswarrior7197", "polish_fighter3000", "rpragchess",
          "nihalsarin", "viditchess", "duhless", "grischuk", "fairchess_on_youtube", "hansontwitch",
          "vincentkeymer", "jefferyx", "penguingm1", "gmbenjaminbok", "jospem", "liemle", "wonderfultime"]
# Well-known media players (any title); most stream blitz, so a lower rapid minimum applies.
MEDIA = ["thechessnerd", "annacramling", "imrosen", "fins0905", "gothamchess"]
POOL, MIN_GAMES, MIN_FAMOUS, MIN_MEDIA, MIN_POOL = 50, 200, 150, 100, 30


def rapid(u):
    """(title, rated rapid games, current rapid rating) for a chess.com user."""
    title = fetch.get_json(f"{fetch.API}/player/{u}").get("title")
    s = fetch.get_json(f"{fetch.API}/player/{u}/stats").get("chess_rapid", {})
    n = sum(s.get("record", {}).get(x, 0) for x in ("win", "loss", "draw"))
    return title, n, s.get("last", {}).get("rating", 0)


def gm_rows(u, group, engine):
    """One player's rapid feature rows; cached per player so a rerun skips finished players."""
    done = fetch.DATA / "gm" / f"{u}.csv"
    if done.exists():
        return pd.read_csv(done)
    print(f"{u}: downloading...", flush=True)
    gs = fetch.games(u, "rapid")
    ten_to_fifteen = [g for g in gs if 600 <= features.parse_tc(g["time_control"])[0] <= 900]
    if len(ten_to_fifteen) >= MIN_GAMES:
        gs = ten_to_fifteen
    t = features.features_table(gs, u, engine)
    t = t[t.who == "player"].assign(pool=group)
    done.parent.mkdir(exist_ok=True)
    t.to_csv(done, index=False)
    return t


def main():
    boards = fetch.get_json(f"{fetch.API}/leaderboards")
    top = [p["username"].lower() for k in ("live_rapid", "live_blitz") for p in boards.get(k, [])]
    info = {}
    for u in dict.fromkeys(FAMOUS + MEDIA + top):
        try:
            info[u] = rapid(u)
        except Exception as e:  # closed accounts
            print("skip", u, e)
    picks = [(u, MIN_FAMOUS, "famous") for u in FAMOUS if u in info and info[u][1] >= MIN_FAMOUS]
    picks += [(u, MIN_MEDIA, "media") for u in MEDIA if u in info and info[u][1] >= MIN_MEDIA]
    picks += [(u, MIN_GAMES, "top") for u in sorted(
        (u for u, (title, n, _) in info.items() if u not in FAMOUS + MEDIA and title == "GM" and n >= MIN_GAMES),
        key=lambda u: -info[u][2])]
    engine = features.open_engine()
    tables = []
    for u, need, group in picks:
        if sum(t.pool.iloc[0] != "media" for t in tables) >= POOL:
            break
        t = gm_rows(u, group, engine)
        print(u, group, len(t), flush=True)
        if len(t) >= need:
            tables.append(t)
    if engine:
        engine.quit()
    if len(tables) < MIN_POOL:
        raise SystemExit(f"only {len(tables)} GMs qualified (need {MIN_POOL})")
    out = pd.concat(tables)
    out.to_csv(fetch.DATA / "gm_games.csv", index=False)
    print(out.groupby("pool").username.nunique().to_dict(), len(out), "games")


if __name__ == "__main__":
    main()
