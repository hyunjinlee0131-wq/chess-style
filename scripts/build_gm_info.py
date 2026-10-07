"""One-off: GM profile details and per-game results for the app's GM cards and reading list.
Writes data/gm_info.csv (chess.com profiles, 1 request per GM) and data/gm_results.csv (opponent + result per
GM game, read from the local archive cache data/raw written by scripts/build_gm_pool.py; no new downloads)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd

from chessstyle import fetch


def gm_result(game, username):
    """(opponent username, 'win' | 'loss' | 'draw') from `username`'s side of a chess.com game dict."""
    me, opp = ("white", "black") if game["white"]["username"].lower() == username.lower() else ("black", "white")
    outcome = "win" if game[me]["result"] == "win" else "loss" if game[opp]["result"] == "win" else "draw"
    return game[opp]["username"], outcome


def main():
    gm = pd.read_csv(fetch.DATA / "gm_games.csv")
    users = sorted(gm.username.unique())
    info = []
    for u in users:
        d = fetch.get_json(f"{fetch.API}/player/{u}")
        info.append({"username": u, "name": d.get("name") or u, "title": d.get("title", ""),
                     "avatar": d.get("avatar", ""), "country": d.get("country", "").rsplit("/", 1)[-1]})
    pd.DataFrame(info).to_csv(fetch.DATA / "gm_info.csv", index=False)

    wanted = set(zip(gm.game, gm.username))
    rows = []
    for u in users:
        for f in sorted((fetch.DATA / "raw" / u).glob("*.json")):
            for g in json.loads(f.read_text(encoding="utf-8"))["games"]:
                if (g.get("url"), u) in wanted:
                    opp, res = gm_result(g, u)
                    rows.append({"game": g["url"], "username": u, "opponent": opp, "result": res})
    out = pd.DataFrame(rows).drop_duplicates(["game", "username"])
    out.to_csv(fetch.DATA / "gm_results.csv", index=False)
    print(len(info), "GMs;", len(out), "of", len(wanted), "GM games with results")


if __name__ == "__main__":
    main()
