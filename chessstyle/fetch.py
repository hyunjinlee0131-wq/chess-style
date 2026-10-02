"""chess.com Published-Data API: game archives with an on-disk cache."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.chess.com/pub"
DATA = Path(__file__).resolve().parent.parent / "data"
HEADERS = {"User-Agent": "chess-style (github.com/hyunjinlee0131-wq)"}


def get_json(url, tries=5):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(2 ** i)


def games(username, time_class="rapid", cache=DATA / "raw"):
    """Rated standard-chess games of `time_class`. Past months are read from cache; the current month is refetched."""
    u = username.lower()
    try:
        months = get_json(f"{API}/player/{u}/games/archives")["archives"]
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(f"chess.com user '{username}' not found") from None
        raise
    now = time.strftime("%Y/%m", time.gmtime())
    out = []
    for url in months:
        ym = url[-7:]  # "YYYY/MM"
        path = Path(cache) / u / (ym.replace("/", "-") + ".json")
        if path.exists() and ym != now:
            data = json.loads(path.read_text(encoding="utf-8"))
        else:
            data = get_json(url)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        out += [g for g in data["games"]
                if g.get("rules") == "chess" and g.get("rated") and g.get("time_class") == time_class and g.get("pgn")]
    return out
