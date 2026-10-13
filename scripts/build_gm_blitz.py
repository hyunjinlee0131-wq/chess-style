"""One-off: blitz GM pool for the app's Rapid/Blitz switch. Same accounts as data/gm_info.csv, each one's 500 most
recent rated blitz games, features with Stockfish -> data/gm_blitz.csv, opponent/result per game ->
data/gm_blitz_results.csv. Archives come from the local cache (only the current month is refetched).
Cached per player in data/gm_blitz/<user>.csv, so a rerun resumes."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd

from chessstyle import features, fetch

N, MIN_GAMES = 500, 200


def player_rows(u, engine):
    done = fetch.DATA / "gm_blitz" / f"{u}.csv"
    if done.exists():
        return pd.read_csv(done)
    games = fetch.games(u, "blitz", limit=N)
    t = features.features_table(games, u, engine)
    t = t[t.who == "player"].assign(pool="blitz")
    res = {g["url"]: fetch.result_for(g, u) for g in games}
    t = t.assign(opponent=t.game.map(lambda x: res[x][0]), result=t.game.map(lambda x: res[x][1]))
    done.parent.mkdir(exist_ok=True)
    t.to_csv(done, index=False)
    return t


def main():
    engine = features.open_engine()
    if engine is None:
        raise SystemExit("Stockfish not found: set STOCKFISH_PATH")
    tables = []
    for u in pd.read_csv(fetch.DATA / "gm_info.csv").username:
        t = player_rows(u, engine)
        print(u, len(t), flush=True)
        if len(t) >= MIN_GAMES:
            tables.append(t)
    engine.quit()
    out = pd.concat(tables)
    out[["game", "username", "opponent", "result"]].to_csv(fetch.DATA / "gm_blitz_results.csv", index=False)
    out.drop(columns=["opponent", "result"]).to_csv(fetch.DATA / "gm_blitz.csv", index=False)
    print(out.username.nunique(), "GMs,", len(out), "blitz games")


if __name__ == "__main__":
    main()
