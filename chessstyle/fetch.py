"""chess.com Published-Data API: game archives with an on-disk cache."""
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.chess.com/pub"
DATA = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "chess-style (github.com/hyunjinlee0131-wq)"}


def get_json(url, tries=5):
    """GET JSON, retrying rate limits (429) and network errors (timeouts, resets) with backoff."""
    for i in range(tries):
        last = i == tries - 1
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or last:
                raise
        except OSError:  # URLError, TimeoutError, ConnectionResetError
            if last:
                raise
        time.sleep(2 ** i)


def games(username, time_class="rapid", cache=DATA / "raw", limit=None):
    """Rated standard-chess games of `time_class`. Past months are read from cache; the current month is refetched.
    With `limit`, months are read newest-first until `limit` games are found; returns the newest `limit`, oldest first."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{3,25}", username):
        raise ValueError(f"'{username}' is not a valid chess.com username")
    u = username.lower()
    try:
        months = get_json(f"{API}/player/{u}/games/archives")["archives"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"chess.com user '{username}' not found") from None
        raise
    now = time.strftime("%Y/%m", time.gmtime())
    chunks = []
    for url in reversed(months) if limit else months:
        ym = url[-7:]  # "YYYY/MM"
        path = Path(cache) / u / (ym.replace("/", "-") + ".json")
        if path.exists() and ym != now:
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = get_json(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        chunks.append([g for g in data["games"]
                       if g.get("rules") == "chess" and g.get("rated") and g.get("time_class") == time_class and g.get("pgn")])
        if limit and sum(map(len, chunks)) >= limit:
            break
    if limit:
        chunks.reverse()
    out = [g for c in chunks for g in c]
    return out[-limit:] if limit else out


def result_for(game, username):
    """(opponent username, 'win' | 'loss' | 'draw') from `username`'s side of a chess.com game dict."""
    me, opp = ("white", "black") if game["white"]["username"].lower() == username.lower() else ("black", "white")
    outcome = "win" if game[me]["result"] == "win" else "loss" if game[opp]["result"] == "win" else "draw"
    return game[opp]["username"], outcome
