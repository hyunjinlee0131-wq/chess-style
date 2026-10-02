# Chess Style Matcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Given a chess.com username, profile the player's rapid style against same-rating peers, chart how it changed as they climbed, and match it to grandmasters, with an honest validation of whether the matching means anything.

**Architecture:** Four plain-function modules (`fetch` → `features` → `profile` → `match`) that both the player and the GM pool flow through. Features come from moves via python-chess, with Stockfish used only to confirm sacrifice candidates. Analysis is told in two executed notebooks, and the results go in the README.

**Tech Stack:** Python 3.13, python-chess, pandas, numpy, scikit-learn (conditional Task 9 only), matplotlib, jupyter/nbformat, pytest. Stockfish binary via `STOCKFISH_PATH`.

**Spec:** `docs/superpowers/specs/2026-10-02-chess-style-design.md`

## Global Constraints

- Repo root: `D:\chess-style`. Commands are Git Bash, run from the repo root. Python is invoked as `.venv/Scripts/python`.
- Dependencies: exactly `python-chess`, `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `jupyter`, `pytest`. No `requests`, no `pyarrow`, no Streamlit (v2).
- chess.com API: base `https://api.chess.com/pub`, serial requests, header `User-Agent: chess-style (github.com/hyunjinlee0131-wq)`, retry with backoff on HTTP 429.
- Any username: lower-case it everywhere; no thresholds tied to the author's account.
- Games kept: `rules == "chess"`, `rated`, `time_class == "rapid"` (GM blitz only as fallback), with a `pgn`, ≥ 20 plies (10 moves).
- "Current" = player rating ≥ latest rating − 150; widen to − 250 if fewer than 200 games.
- Bands: ≤ 5 equal-count quantile bands over player games rated ≥ 1000, at least 100 games per band; below 1000 → no band.
- Opening families with < 20 reference games in a cohort merge into `other|<side>`.
- GM pool: ≥ 200 rapid games, ~50 GMs, base time 600–900 s if that still leaves ≥ 200 games; blitz fallback if < 30 GMs.
- Validation pass bar: top-5 accuracy ≥ 30% at 100-game chunks, train fraction 0.5 (time split).
- `data/` gitignored except `data/gm_games.csv`.
- Every commit message ends with the line `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never push to GitHub; publishing is the author's decision.

## Review Focus

1. Unknown username → a clear `ValueError("chess.com user '...' not found")`, not a raw HTTP traceback (Task 1 test).
2. Games without `%clk` comments (old or odd games) → time features NaN, no crash (Task 2 test).
3. Aborted or very short games, or a game dict missing `pgn` → skipped silently (Task 3 test).
4. A player with too few games rated 1000+ (new or low-rated accounts) → a clear `ValueError` naming the requirement (Task 4 test).
5. A feature that is constant in the reference cohort, or NaN in a GM vector → NaN z-score / ignored dimension, never `inf` or a NaN similarity (Task 4 and Task 5 tests).

---

### Task 1: Scaffold + chess.com fetcher

**Files:**
- Create: `requirements.txt`, `pytest.ini`, `.gitignore`, `chessstyle/__init__.py` (empty), `chessstyle/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Produces: `fetch.API: str`, `fetch.DATA: pathlib.Path` (repo `data/`), `fetch.get_json(url: str) -> dict`, `fetch.games(username: str, time_class: str = "rapid", cache: Path = DATA / "raw") -> list[dict]` (raw chess.com game dicts with keys `url, pgn, end_time, time_control, rated, rules, time_class, white{username,rating}, black{username,rating}`).

- [ ] **Step 1: Scaffold files and environment**

`requirements.txt`:
```
python-chess
pandas
numpy
scikit-learn
matplotlib
jupyter
pytest
```
`pytest.ini`:
```
[pytest]
pythonpath = .
testpaths = tests
```
`.gitignore`:
```
.venv/
__pycache__/
.ipynb_checkpoints/
data/*
!data/gm_games.csv
```
Then:
```bash
py -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
mkdir -p chessstyle tests scripts notebooks data && touch chessstyle/__init__.py
```

- [ ] **Step 2: Write the failing tests** — `tests/test_fetch.py`

```python
import urllib.error

import pytest

from chessstyle import fetch


def fake_api(calls):
    def get_json(url):
        calls.append(url)
        if url.endswith("/games/archives"):
            return {"archives": [f"{fetch.API}/player/me/games/2025/05"]}
        return {"games": [
            {"rules": "chess", "rated": True, "time_class": "rapid", "pgn": "1. e4 *", "url": "a"},
            {"rules": "chess960", "rated": True, "time_class": "rapid", "pgn": "1. e4 *", "url": "b"},
            {"rules": "chess", "rated": False, "time_class": "rapid", "pgn": "1. e4 *", "url": "c"},
            {"rules": "chess", "rated": True, "time_class": "blitz", "pgn": "1. e4 *", "url": "d"},
            {"rules": "chess", "rated": True, "time_class": "rapid", "url": "e"},
        ]}
    return get_json


def test_games_filters_and_caches_past_months(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fetch, "get_json", fake_api(calls))
    assert [g["url"] for g in fetch.games("Me", cache=tmp_path)] == ["a"]
    assert [g["url"] for g in fetch.games("Me", cache=tmp_path)] == ["a"]
    assert sum(c.endswith("/2025/05") for c in calls) == 1
    assert (tmp_path / "me" / "2025-05.json").exists()


def test_unknown_user_is_a_clear_error(monkeypatch):
    def get_json(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
    monkeypatch.setattr(fetch, "get_json", get_json)
    with pytest.raises(ValueError, match="not found"):
        fetch.games("nobody-xyz")
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_fetch.py -v`
Expected: FAIL / ERROR, `ImportError: cannot import name 'fetch'`

- [ ] **Step 4: Implement** — `chessstyle/fetch.py`

```python
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
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_fetch.py -v`
Expected: 2 passed

- [ ] **Step 6: Smoke-test against the real API** (two requests)

```bash
.venv/Scripts/python -c "from chessstyle import fetch; print(fetch.get_json(fetch.API + '/player/hikaru')['username'])"
.venv/Scripts/python -c "from chessstyle import fetch
try: fetch.games('no-such-user-zz9')
except ValueError as e: print(e)"
```
Expected: `hikaru`, then `chess.com user 'no-such-user-zz9' not found`.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt pytest.ini .gitignore chessstyle tests/test_fetch.py
git commit -m "feat: chess.com archive fetcher with cache

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Move-based style features

**Files:**
- Create: `chessstyle/features.py`
- Test: `tests/test_features.py`

**Interfaces:**
- Produces: `features.parse_tc(tc: str) -> tuple[int, int]`, `features.material(board, color) -> int`, `features.opening_family(sans: list[str]) -> str`, `features.extract(pgn: str, engine=None, depth: int = 10, min_plies: int = 20) -> dict | None` returning `{"white": f, "black": f}` where `f` has exactly these keys: `checks, captures, sacrifices, early_queen, castled, castle_move, castle_long, opposite_castle, pawn_storm, queen_trade, queen_trade_move, material_30, endgame, game_len, bishop_takes_knight, bishop_pair_kept, pawn_share, time_open, time_mid, time_end, time_trouble, material_blunders, family`. Missing values are `float("nan")`. In this task `sacrifices` and `material_blunders` are always NaN (the engine arrives in Task 3).

- [ ] **Step 1: Write the failing tests** — `tests/test_features.py`

```python
import math

from chessstyle import features

HDR = '[Event "t"]\n[TimeControl "600"]\n[Result "*"]\n\n'
CASTLE = HDR + (
    "1. e4 {[%clk 0:09:58]} e5 {[%clk 0:09:57]} 2. Nf3 {[%clk 0:09:50]} Nc6 {[%clk 0:09:55]} "
    "3. Bc4 {[%clk 0:09:40]} Bc5 {[%clk 0:09:50]} 4. c3 {[%clk 0:09:30]} Nf6 {[%clk 0:09:45]} "
    "5. d3 {[%clk 0:09:20]} d6 {[%clk 0:09:40]} 6. O-O {[%clk 0:09:10]} O-O {[%clk 0:09:35]} "
    "7. Re1 {[%clk 0:09:00]} a6 {[%clk 0:09:30]} 8. a4 {[%clk 0:08:50]} Ba7 {[%clk 0:09:25]} "
    "9. h3 {[%clk 0:08:40]} h6 {[%clk 0:09:20]} 10. Nbd2 {[%clk 0:08:30]} Re8 {[%clk 0:09:15]} *")
QUEENS = HDR + (
    "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qe5+ 4. Qe2 Qxe2+ 5. Bxe2 Nf6 6. Nf3 Bf5 "
    "7. d3 e6 8. Bd2 Bb4 9. O-O-O Nc6 10. a3 Ba5 *")


def test_castling_clock_and_basics():
    w = features.extract(CASTLE)["white"]
    assert (w["castled"], w["castle_move"], w["castle_long"], w["opposite_castle"]) == (1, 6, 0, 0)
    assert w["time_open"] == 90 / 600 and math.isnan(w["time_mid"]) and w["time_trouble"] == 0
    assert w["checks"] == 0 and w["pawn_share"] == 0.5 and w["game_len"] == 10
    assert w["family"] == "open" and w["queen_trade"] == 0
    assert math.isnan(w["material_30"]) and math.isnan(w["sacrifices"])


def test_queen_trade_long_castle_checks_and_no_clocks():
    f = features.extract(QUEENS)
    w, b = f["white"], f["black"]
    assert w["queen_trade"] == 1 and w["queen_trade_move"] == 5
    assert (w["castle_move"], w["castle_long"]) == (9, 1)
    assert b["castled"] == 0 and math.isnan(b["castle_move"]) and math.isnan(w["opposite_castle"])
    assert w["captures"] == 0.2 and b["checks"] == 0.2
    assert w["early_queen"] == 1 and b["early_queen"] == 1
    assert w["family"] == "scandinavian"
    assert math.isnan(w["time_open"]) and math.isnan(w["time_trouble"])


def test_short_game_skipped_and_time_control_parsing():
    assert features.extract(HDR + "1. e4 e5 2. Nf3 *") is None
    assert features.parse_tc("600") == (600, 0) and features.parse_tc("600+5") == (600, 5)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_features.py -v`
Expected: FAIL, `ImportError: cannot import name 'features'`

- [ ] **Step 3: Implement** — `chessstyle/features.py`

```python
"""Per-game style features from a chess.com PGN (python-chess; engine optional)."""
import io
import math

import chess
import chess.engine
import chess.pgn

NAN = float("nan")
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
E4_REPLIES = {"c5": "sicilian", "e5": "open", "e6": "french", "c6": "caro-kann", "d5": "scandinavian"}
D4_REPLIES = {"d5": "closed", "Nf6": "indian"}


def parse_tc(tc):
    """'600' -> (600, 0); '600+5' -> (600, 5)."""
    base, _, inc = tc.partition("+")
    return int(base), int(inc or 0)


def material(board, color):
    return sum(v * len(board.pieces(p, color)) for p, v in VALUES.items())


def non_pawn_material(board):
    return sum(material(board, c) - len(board.pieces(chess.PAWN, c)) for c in chess.COLORS)


def opening_family(sans):
    first, reply = (sans + ["", ""])[:2]
    if first == "e4":
        return E4_REPLIES.get(reply, "e4-other")
    if first == "d4":
        return D4_REPLIES.get(reply, "d4-other")
    return {"c4": "english", "Nf3": "reti"}.get(first, "other")


def _castling(color, boards, moves):
    """(own move number, 1 if queenside else 0) of `color`'s castling, or (NAN, NAN)."""
    k = 0
    for b, m in zip(boards, moves):
        if b.turn == color:
            k += 1
            if b.is_castling(m):
                return k, int(not b.is_kingside_castling(m))
    return NAN, NAN


def _time(own_clocks, base, inc):
    keys = ("time_open", "time_mid", "time_end", "time_trouble")
    if not own_clocks or None in own_clocks or not base:
        return dict.fromkeys(keys, NAN)
    total = base + inc * len(own_clocks)
    spent, prev = [], base
    for c in own_clocks:
        spent.append(prev - c + inc)
        prev = c
    phase = lambda s: sum(s) / total if s else NAN
    return {"time_open": phase(spent[:10]), "time_mid": phase(spent[10:30]), "time_end": phase(spent[30:]),
            "time_trouble": int(min(own_clocks) < 0.1 * base)}


def _swings(color, own, boards, engine, depth):
    """Placeholder until Task 3 adds the engine check: no engine -> NaN."""
    return {"sacrifices": NAN, "material_blunders": NAN}


def _side(color, own, boards, moves, clocks, base, inc, engine, depth):
    n = len(own)
    checks = captures = pawn_moves = storms = bxn = early_queen = 0
    for k, i in enumerate(own, start=1):
        b, m = boards[i], moves[i]
        piece = b.piece_type_at(m.from_square)
        checks += b.gives_check(m)
        captures += b.is_capture(m)
        early_queen |= piece == chess.QUEEN and k < 8
        bxn += piece == chess.BISHOP and b.piece_type_at(m.to_square) == chess.KNIGHT
        if piece == chess.PAWN:
            pawn_moves += 1
            rank = chess.square_rank(m.to_square) if color else 7 - chess.square_rank(m.to_square)
            near_king = abs(chess.square_file(m.to_square) - chess.square_file(b.king(not color))) <= 1
            storms += k > 10 and rank >= 3 and near_king
    return {
        "checks": checks / n, "captures": captures / n, "early_queen": int(early_queen),
        "pawn_storm": storms / n, "bishop_takes_knight": bxn, "pawn_share": pawn_moves / n,
        "bishop_pair_kept": int(len(boards[40].pieces(chess.BISHOP, color)) >= 2) if len(boards) > 40 else NAN,
        **_time([clocks[i] for i in own], base, inc),
        **_swings(color, own, boards, engine, depth),
    }


def extract(pgn, engine=None, depth=10, min_plies=20):
    """PGN text -> {"white": features, "black": features}, or None if shorter than `min_plies`."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    base, inc = parse_tc(game.headers.get("TimeControl", "0"))
    board = game.board()
    boards, moves, clocks = [board.copy(stack=False)], [], []  # boards[i] = position before ply i
    for node in game.mainline():
        moves.append(node.move)
        clocks.append(node.clock())
        board.push(node.move)
        boards.append(board.copy(stack=False))
    if len(moves) < min_plies:
        return None
    queenless = [i for i, b in enumerate(boards)
                 if not b.pieces(chess.QUEEN, chess.WHITE) and not b.pieces(chess.QUEEN, chess.BLACK)]
    shared = {
        "queen_trade": int(bool(queenless)),
        "queen_trade_move": boards[queenless[0] - 1].fullmove_number if queenless else NAN,
        "material_30": material(boards[60], chess.WHITE) + material(boards[60], chess.BLACK) if len(boards) > 60 else NAN,
        "endgame": int(any(non_pawn_material(b) <= 13 for b in boards)),
        "game_len": (len(moves) + 1) // 2,
        "family": opening_family([boards[i].san(m) for i, m in enumerate(moves[:2])]),
    }
    castle = {c: _castling(c, boards, moves) for c in chess.COLORS}
    out = {}
    for color in chess.COLORS:
        own = [i for i in range(len(moves)) if boards[i].turn == color]
        f = _side(color, own, boards, moves, clocks, base, inc, engine, depth)
        move_no, long_ = castle[color]
        other = castle[not color][1]
        f.update(shared, castled=int(not math.isnan(move_no)), castle_move=move_no, castle_long=long_,
                 opposite_castle=NAN if math.isnan(long_) or math.isnan(other) else int(long_ != other))
        out["white" if color else "black"] = f
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_features.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add chessstyle/features.py tests/test_features.py
git commit -m "feat: move-based style features per game

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Engine sacrifice check + features table

**Files:**
- Modify: `chessstyle/features.py` (replace `_swings`; add `open_engine`, `_eval`, `features_table`; add `import os`, `import pandas as pd`)
- Test: `tests/test_features.py` (append)

**Interfaces:**
- Consumes: `extract` from Task 2.
- Produces: `features.open_engine() -> chess.engine.SimpleEngine | None`; `features.features_table(games: list[dict], username: str, engine=None) -> pd.DataFrame` with columns `game, end_time, who ('player'|'opponent'), username (lower), side, rating, player_rating, time_control` + every feature key from Task 2.

- [ ] **Step 1: Install Stockfish (one-off, manual)**

Download the Windows build from https://stockfishchess.org/download/, unzip it to `D:\tools\stockfish\`, then set the variable to the `.exe` inside (exact filename varies by build):
```bash
setx STOCKFISH_PATH "D:\tools\stockfish\stockfish\stockfish-windows-x86-64-avx2.exe"
```
Open a new terminal so the variable is visible. Check: `.venv/Scripts/python -c "import os; print(os.environ['STOCKFISH_PATH'])"`.

- [ ] **Step 2: Write the failing tests** — append to `tests/test_features.py`

```python
import pytest

HUNG = HDR + "1. e4 e5 2. Qh5 Nc6 3. Qxe5+ Nxe5 *"
LEGAL = HDR + "1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# *"


@pytest.fixture(scope="module")
def engine():
    e = features.open_engine()
    if e is None:
        pytest.skip("STOCKFISH_PATH not set")
    yield e
    e.quit()


def test_hung_queen_is_blunder_not_sacrifice(engine):
    w = features.extract(HUNG, engine, min_plies=0)["white"]
    assert (w["sacrifices"], w["material_blunders"]) == (0, 1)


def test_sound_queen_offer_is_sacrifice(engine):
    f = features.extract(LEGAL, engine, min_plies=0)
    assert (f["white"]["sacrifices"], f["white"]["material_blunders"]) == (1, 0)
    assert f["black"]["sacrifices"] == 0


def test_features_table_rows_and_skips():
    g = {"url": "u1", "end_time": 1, "time_control": "600", "pgn": CASTLE,
         "white": {"username": "Me", "rating": 1700}, "black": {"username": "Opp", "rating": 1720}}
    short = dict(g, url="u2", pgn=HDR + "1. e4 e5 *")
    no_pgn = {k: v for k, v in g.items() if k != "pgn"}
    stranger = dict(g, url="u3", white={"username": "x", "rating": 1}, black={"username": "y", "rating": 1})
    t = features.features_table([g, short, no_pgn, stranger], "me")
    assert list(t.who) == ["player", "opponent"]
    assert list(t.rating) == [1700, 1720] and list(t.player_rating) == [1700, 1700]
    assert list(t.username) == ["me", "opp"]
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_features.py -v`
Expected: the 3 new tests FAIL (`AttributeError: ... 'open_engine'` / `'features_table'`); the 3 old tests pass.

- [ ] **Step 4: Implement**: in `chessstyle/features.py` add `import os` and `import pandas as pd` to the imports, replace the placeholder `_swings`, and add the new functions:

```python
def open_engine():
    """Stockfish from $STOCKFISH_PATH, or None (sacrifice/blunder features then stay NaN)."""
    path = os.environ.get("STOCKFISH_PATH")
    return chess.engine.SimpleEngine.popen_uci(path) if path else None


def _eval(engine, board, color, depth):
    info = engine.analyse(board, chess.engine.Limit(depth=depth))
    return info["score"].pov(color).score(mate_score=10000)


def _swings(color, own, boards, engine, depth):
    """Own moves after which material is down >= 2 after the reply and still 2 moves later.
    The engine splits them: eval drop < 1 pawn = sacrifice, otherwise a material blunder."""
    if engine is None:
        return {"sacrifices": NAN, "material_blunders": NAN}
    sac = blunder = 0
    last = len(boards) - 1
    bal = lambda b: material(b, color) - material(b, not color)
    for i in own:
        b0 = bal(boards[i])
        if bal(boards[min(i + 2, last)]) <= b0 - 2 and bal(boards[min(i + 4, last)]) <= b0 - 2:
            if _eval(engine, boards[i], color, depth) - _eval(engine, boards[i + 1], color, depth) < 100:
                sac += 1
            else:
                blunder += 1
    return {"sacrifices": sac, "material_blunders": blunder}


def features_table(games, username, engine=None):
    """chess.com game dicts -> one row per side ('player' = username, else 'opponent'). Short games skipped."""
    u, rows = username.lower(), []
    for g in games:
        me = next((s for s in ("white", "black") if g[s]["username"].lower() == u), None)
        if me is None or not g.get("pgn"):
            continue
        feats = extract(g["pgn"], engine)
        if feats is None:
            continue
        for side in ("white", "black"):
            rows.append({"game": g["url"], "end_time": g["end_time"], "who": "player" if side == me else "opponent",
                         "username": g[side]["username"].lower(), "side": side, "rating": g[side]["rating"],
                         "player_rating": g[me]["rating"], "time_control": g["time_control"], **feats[side]})
    return pd.DataFrame(rows)
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_features.py -v`
Expected: 6 passed (the 2 engine tests show `skipped` if `STOCKFISH_PATH` is unset; set it before moving on).

- [ ] **Step 6: Commit**

```bash
git add chessstyle/features.py tests/test_features.py
git commit -m "feat: engine-checked sacrifices and per-side features table

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Bands, opening adjustment, peer z-scores

**Files:**
- Create: `chessstyle/profile.py`
- Test: `tests/test_profile.py`

**Interfaces:**
- Consumes: a features table (Task 3 columns).
- Produces: `profile.GROUPS: dict[str, list[str]]`, `profile.FEATURES: list[str]` (21 names, in GROUPS order), `profile.INTERACTIVE: set[str]`, `profile.assign_bands(df, n=5, min_rating=1000, min_per_band=100) -> DataFrame` (adds float `band`, NaN below `min_rating`), `profile.current_mask(df, window=150, min_games=200) -> bool Series`, `profile.normalise(df, ref, group=None, min_family=20, by_opening=True) -> DataFrame` (copy, FEATURES replaced by z-scores, adds `fam`), `profile.player_frame(table) -> (z: DataFrame, current: bool Series)`, `profile.vectors(z) -> DataFrame` (index username, columns FEATURES).

- [ ] **Step 1: Write the failing tests** — `tests/test_profile.py`

```python
import numpy as np
import pandas as pd
import pytest

from chessstyle import profile

F = profile.FEATURES


def table(n_games, rating_of, seed=0):
    """Synthetic features table: player alternates colours, two opening families."""
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n_games):
        r = rating_of(i)
        family = ("french", "sicilian")[i % 4 // 2]
        me = "white" if i % 2 == 0 else "black"
        for who, side in (("player", me), ("opponent", "black" if me == "white" else "white")):
            rows.append({"game": i, "end_time": i, "who": who, "side": side, "rating": r, "player_rating": r,
                         "username": who, "family": family, **dict(zip(F, rng.normal(size=len(F))))})
    return pd.DataFrame(rows)


def test_normalise_centres_families_and_scales():
    df = profile.assign_bands(table(800, lambda i: 1000 + i))
    ref = df.who == "opponent"
    r = profile.normalise(df, ref, group="band", min_family=5)[ref]
    assert np.allclose(r.groupby(["band", "fam"])[F].mean(), 0, atol=1e-9)
    assert np.allclose(r.groupby("band")[F].std(), 1)


def test_bands_equal_count_and_below_1000_excluded():
    df = profile.assign_bands(table(700, lambda i: 500 + 2 * i))
    p = df[df.who == "player"]
    assert p[p.player_rating < 1000].band.isna().all()
    counts = p.band.value_counts()
    assert len(counts) == 4 and counts.max() - counts.min() <= 1


def test_too_few_games_is_a_clear_error():
    with pytest.raises(ValueError, match="at least 100"):
        profile.assign_bands(table(150, lambda i: 600))


def test_current_window_widens_when_too_few_games():
    df = table(400, lambda i: 1000 + 2 * i)  # latest 1798; only 76 games >= 1648 -> widen to 1548
    m = profile.current_mask(df)
    assert (df[m].who == "player").all() and df[m].rating.min() == 1548


def test_constant_feature_gives_nan_not_inf():
    df = profile.assign_bands(table(800, lambda i: 1000 + i))
    df["castled"] = 1.0
    z = profile.normalise(df, df.who == "opponent", group="band", min_family=5)
    assert z.castled.isna().all()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_profile.py -v`
Expected: FAIL, `ImportError: cannot import name 'profile'`

- [ ] **Step 3: Implement** — `chessstyle/profile.py`

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_profile.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add chessstyle/profile.py tests/test_profile.py
git commit -m "feat: rating bands, opening adjustment and peer z-scores

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Matching, uncertainty, reading list, identification

**Files:**
- Create: `chessstyle/match.py`
- Test: `tests/test_match.py`

**Interfaces:**
- Consumes: `profile.FEATURES`, `profile.normalise`.
- Produces: `match.similarities(vec: Series, profiles: DataFrame) -> Series` (cosine per profile row, NaN dims ignored), `match.explain(vec, gm_vec, k=3) -> {"shared": list[str], "differs": str | None}`, `match.bootstrap(rows: DataFrame, profiles, n=1000, top=3, seed=0) -> DataFrame[sim, lo, hi, p_top]` sorted by `sim` desc, `match.reading_list(gm_games, gm, fams, n=10) -> list[str]` (game URLs), `match.identify(gm_games, chunk=100, train_frac=0.5, by_opening=True, shuffle=False, drop=None, seed=0) -> {"top1", "top5", "chance_top5", "tests"}`.

- [ ] **Step 1: Write the failing tests** — `tests/test_match.py`

```python
import numpy as np
import pandas as pd
import pytest

from chessstyle import match, profile

F = profile.FEATURES


def profiles():
    """Three GMs defined only on the first 4 features; the rest are NaN."""
    return pd.DataFrame([[2, 1, 0, -1], [2, 1, 0, 1], [-2, -1, 0, 1]],
                        index=["a", "b", "c"], columns=F[:4], dtype=float).reindex(columns=F)


def test_self_is_top_match_and_nan_dims_ignored():
    P = profiles()
    s = match.similarities(P.loc["a"], P)
    assert s["a"] == pytest.approx(1) and s.idxmax() == "a" and s.notna().all()


def test_explain_shared_and_differs():
    P = profiles()
    e = match.explain(P.loc["a"], P.loc["b"])
    assert e == {"shared": [F[0], F[1], F[2]], "differs": F[3]}


def test_bootstrap_identical_player_always_top():
    P = profiles()
    b = match.bootstrap(pd.DataFrame([P.loc["a"]] * 30), P, n=50)
    assert b.index[0] == "a" and b.loc["a", "p_top"] == 1


def gm_table(n_gm=6, n_games=240, noise=0.5, seed=0):
    rng = np.random.default_rng(seed)
    centres = rng.normal(size=(n_gm, len(F)))
    rows = [{"username": f"gm{g}", "end_time": i, "side": ("white", "black")[i % 2], "family": "open",
             "game": f"g{g}-{i}", **dict(zip(F, centres[g] + noise * rng.normal(size=len(F))))}
            for g in range(n_gm) for i in range(n_games)]
    return pd.DataFrame(rows)


def test_identify_finds_distinct_gms_and_shuffle_is_near_chance():
    t = gm_table()
    assert match.identify(t, chunk=25)["top1"] > 0.9
    assert match.identify(t, chunk=25, shuffle=True)["top1"] < 0.5


def test_reading_list_filters_gm_and_opening_newest_first():
    t = gm_table(n_gm=2, n_games=6)
    assert match.reading_list(t, "gm0", ["open|white"], n=2) == ["g0-4", "g0-2"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_match.py -v`
Expected: FAIL, `ImportError: cannot import name 'match'`

- [ ] **Step 3: Implement** — `chessstyle/match.py`

```python
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
```

- [ ] **Step 4: Run all tests**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all passed (16 total: 2 fetch, 6 features, 5 profile, 5 match).

- [ ] **Step 5: Commit**

```bash
git add chessstyle/match.py tests/test_match.py
git commit -m "feat: cosine matching, bootstrap, reading list, GM identification

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Build the GM pool

**Files:**
- Create: `scripts/build_gm_pool.py`
- Create (output, committed): `data/gm_games.csv`

**Interfaces:**
- Consumes: `fetch.get_json`, `fetch.games`, `fetch.API`, `fetch.DATA`, `features.open_engine`, `features.parse_tc`, `features.features_table`.
- Produces: `data/gm_games.csv`, i.e. GM rows only (`who == "player"`) of the Task 3 table plus a `pool` column (`"rapid"` or `"blitz"`).

- [ ] **Step 1: Write the script** — `scripts/build_gm_pool.py`

```python
"""One-off: pick ~50 GMs with >= 200 rated rapid games and save their per-game features to data/gm_games.csv.
Slow (downloads every monthly archive for each GM, often 1–2 hours) but resumable: archives are cached."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd

from chessstyle import features, fetch

FAMOUS = ["magnuscarlsen", "hikaru", "fabianocaruana", "gmwso", "lachesisq", "firouzja2003",
          "anishgiri", "levonaronian", "chesswarrior7197", "penguingm1"]
POOL, MIN_GAMES, MIN_POOL = 50, 200, 30


def counts(u):
    d = fetch.get_json(f"{fetch.API}/player/{u}/stats")
    n = lambda k: sum(d.get(k, {}).get("record", {}).get(x, 0) for x in ("win", "loss", "draw"))
    return n("chess_rapid"), n("chess_blitz")


def gm_rows(u, time_class, engine):
    gs = fetch.games(u, time_class)
    ten_to_fifteen = [g for g in gs if 600 <= features.parse_tc(g["time_control"])[0] <= 900]
    if len(ten_to_fifteen) >= MIN_GAMES:
        gs = ten_to_fifteen
    t = features.features_table(gs, u, engine)
    return t[t.who == "player"].assign(pool=time_class)


def main():
    gms = fetch.get_json(f"{fetch.API}/titled/GM")["players"]
    c = {}
    for i, u in enumerate(gms):
        try:
            c[u] = counts(u)
        except Exception as e:  # deleted/closed accounts
            print("skip", u, e)
        if i % 100 == 0:
            print(f"stats {i}/{len(gms)}")
    engine = features.open_engine()
    tables = []
    for time_class, col in (("rapid", 0), ("blitz", 1)):
        if time_class == "blitz" and len(tables) >= MIN_POOL:
            break
        taken = {t.username.iloc[0] for t in tables}
        cands = sorted((u for u in c if c[u][col] >= MIN_GAMES and u not in taken),
                       key=lambda u: (u not in FAMOUS, -c[u][col]))
        goal = POOL if time_class == "rapid" else MIN_POOL
        for u in cands:
            if len(tables) >= goal:
                break
            t = gm_rows(u, time_class, engine)
            print(u, time_class, len(t))
            if len(t) >= MIN_GAMES:
                tables.append(t)
    if engine:
        engine.quit()
    out = pd.concat(tables)
    out.to_csv(fetch.DATA / "gm_games.csv", index=False)
    print(out.groupby("pool").username.nunique(), len(out), "games")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it** (long; run in the background or a spare terminal, with `STOCKFISH_PATH` set)

Run: `.venv/Scripts/python scripts/build_gm_pool.py`
Expected: ends by printing the GM count per pool (rapid ≈ 50, no blitz row expected) and the total games (≈ 15k–30k). If interrupted, rerun: cached archives make it fast.

- [ ] **Step 3: Sanity-check the output**

```bash
.venv/Scripts/python -c "import pandas as pd; g=pd.read_csv('data/gm_games.csv'); print(g.username.nunique(), len(g), g.groupby('username').size().min(), g.sacrifices.isna().mean())"
```
Expected: ~50 GMs, min games per GM ≥ 200, sacrifice NaN share `0.0` (it is `1.0` if the engine wasn't found; fix `STOCKFISH_PATH` and rerun). Also note the oldest/newest `end_time` per GM for the README (spec: state how old the games are).

- [ ] **Step 4: Commit**

```bash
git add scripts/build_gm_pool.py data/gm_games.csv
git commit -m "feat: GM rapid pool and per-game features

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Notebook 01: my style

**Files:**
- Create: `scripts/py2nb.py`, `notebooks/01_my_style.py` (source), `notebooks/01_my_style.ipynb` (executed output)

**Interfaces:**
- Consumes: everything from Tasks 1–6. Reads the username from the env var `CHESS_USERNAME`.

- [ ] **Step 1: Write the converter** — `scripts/py2nb.py`

```python
"""Percent-format .py ('# %%' cells) -> .ipynb next to it."""
import sys
from pathlib import Path

import nbformat as nbf

src = Path(sys.argv[1])
cells = [c.strip() for c in src.read_text(encoding="utf-8").split("# %%") if c.strip()]
nbf.write(nbf.v4.new_notebook(cells=[nbf.v4.new_code_cell(c) for c in cells]), src.with_suffix(".ipynb"))
```

- [ ] **Step 2: Write the notebook source** — `notebooks/01_my_style.py`

```python
# %%
import os
import sys

sys.path.insert(0, "..")
import matplotlib.pyplot as plt
import pandas as pd

from chessstyle import features, fetch, match, profile

USERNAME = os.environ["CHESS_USERNAME"]

# %%
games = fetch.games(USERNAME)
engine = features.open_engine()
table = features.features_table(games, USERNAME, engine)
if engine:
    engine.quit()
print(len(games), "rated rapid games;", (table.who == "player").sum(), "analysed (10+ moves)")

# %% Style profile: current games vs same-rating peers
z, cur = profile.player_frame(table)
me = z[cur]
vec = me[profile.FEATURES].mean()
print(f"current games: {cur.sum()} (rating {me.rating.min()}–{me.rating.max()})")
for group, fs in profile.GROUPS.items():
    print(f"\n{group}: {vec[fs].mean():+.2f}σ")
    for f in fs:
        print(f"  {f:<20}{vec[f]:+.2f}σ{'  *both players shape this' if f in profile.INTERACTIVE else ''}")

# %% Openings and material blunders (raw, not z-scored)
mine = table[cur]
print((mine.family + " as " + mine.side).value_counts(normalize=True).head(6).round(2))
peers = table[table.game.isin(mine.game) & (table.who == "opponent")]
print(f"material blunders/game: you {mine.material_blunders.mean():.2f}, peers {peers.material_blunders.mean():.2f}")

# %% Climb: style vs same-band peers across rating bands
p = z[(z.who == "player") & z.band.notna()]
labels = table.loc[p.index].groupby(p.band).player_rating.agg(lambda r: f"{r.min()}–{r.max()}")
climb = pd.DataFrame({g: p.groupby("band")[fs].mean().mean(axis=1) for g, fs in profile.GROUPS.items()})
climb.index = labels.loc[climb.index]
climb.plot(marker="o", figsize=(9, 4), title="Style vs same-rating peers as rating climbed (σ)")
plt.axhline(0, color="grey", lw=0.5)
plt.show()

# %% GM matches with reasons and uncertainty
gm = pd.read_csv(fetch.DATA / "gm_games.csv")
P = profile.vectors(profile.normalise(gm, gm.username.notna()))
boot = match.bootstrap(me, P)
for u, r in boot.head(5).iterrows():
    e = match.explain(vec, P.loc[u])
    print(f"{u:<20} {r.sim:.2f} [{r.lo:.2f}, {r.hi:.2f}]  P(top3)={r.p_top:.0%}  "
          f"shared: {', '.join(e['shared'])}  differs: {e['differs']}")

# %% Repertoire matches and reading list
fams = (mine.family + "|" + mine.side).value_counts().head(3).index
print((gm.family + "|" + gm.side).isin(fams).groupby(gm.username).mean().nlargest(5).round(2))
for url in match.reading_list(gm, boot.index[0], fams):
    print(url)

# %% Stability: do the two halves of my current games agree?
m = me.sort_values("end_time")
half = len(m) // 2
a = match.similarities(m.iloc[:half][profile.FEATURES].mean(), P).nlargest(5).index
b = match.similarities(m.iloc[half:][profile.FEATURES].mean(), P).nlargest(5).index
print("top-5 overlap between halves:", len(set(a) & set(b)), "/ 5")
```

- [ ] **Step 3: Build and execute**

```bash
.venv/Scripts/python scripts/py2nb.py notebooks/01_my_style.py
CHESS_USERNAME=<author's chess.com username> .venv/Scripts/python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_my_style.ipynb
```
Expected: no errors. Open the `.ipynb` and check that the profile, climb chart, top-5 GMs with intervals, reading-list URLs and stability overlap are all present.

- [ ] **Step 4: Commit**

```bash
git add scripts/py2nb.py notebooks/01_my_style.py notebooks/01_my_style.ipynb
git commit -m "feat: my-style notebook (profile, climb, GM matches, reading list)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Notebook 02: validation, plus README write-up

**Files:**
- Create: `notebooks/02_validation.py`, `notebooks/02_validation.ipynb`, `README.md`

**Interfaces:**
- Consumes: `match.identify`, `profile.FEATURES`, `data/gm_games.csv`.

- [ ] **Step 1: Write the notebook source** — `notebooks/02_validation.py`

```python
# %%
import sys

sys.path.insert(0, "..")
import pandas as pd

from chessstyle import fetch, match, profile

gm = pd.read_csv(fetch.DATA / "gm_games.csv")
print(gm.username.nunique(), "GMs,", len(gm), "games")

# %% 1. Identification accuracy by chunk size (train = earliest 50%)
pd.DataFrame({c: match.identify(gm, chunk=c) for c in (25, 50, 100)}).T

# %% 2. Opening ablation
pd.DataFrame({"opening-adjusted": match.identify(gm, 100), "raw": match.identify(gm, 100, by_opening=False)}).T

# %% 3. Permutation importance (top-5 drop when one feature is shuffled across test games)
base = match.identify(gm, 100)["top5"]
imp = pd.Series({f: base - match.identify(gm, 100, drop=f)["top5"] for f in profile.FEATURES}).sort_values()
imp.plot.barh(figsize=(6, 7), title="Top-5 accuracy drop when feature is shuffled")

# %% 4. Sanity: shuffled GM labels must land at chance
match.identify(gm, 100, shuffle=True)

# %% Verdict against the pre-registered bar
print("PASS" if base >= 0.30 else "FAIL", f"top-5 @ 100 games = {base:.0%} (bar 30%)")
```

- [ ] **Step 2: Build and execute**

```bash
.venv/Scripts/python scripts/py2nb.py notebooks/02_validation.py
.venv/Scripts/python -m jupyter nbconvert --to notebook --execute --inplace notebooks/02_validation.ipynb
```
Expected: runs clean; the shuffled-label top-5 is close to `chance_top5`. If not, stop: that's a bug, not a result.

- [ ] **Step 3: Write `README.md`** using the actual numbers from both executed notebooks

```markdown
# Which grandmaster plays like me?

Style profiling and grandmaster matching for any chess.com rapid player, measured against
players of the **same rating**, adjusted for **openings**, with an honest validation.

## Question
<one paragraph: rating ≠ style; match on style once strength and repertoire are removed>

## Data
- Player: chess.com Published-Data API, rated 10-min rapid games (N = <from 01>).
- Peer baseline: the opponents' side of the same games, in 5 equal-count rating bands.
- GMs: <n> GMs with ≥ 200 rated rapid games (N = <games>, played <oldest>–<newest>).

## Method
21 move-based features (python-chess) in 5 groups; Stockfish only to tell sacrifices from blunders.
Opening-family adjustment → z-scores vs same-band peers (player) / GM pool (GMs) →
cosine similarity, 1,000-sample bootstrap for uncertainty.

## Results
- My profile: <3 strongest traits from 01>
- My climb: <one sentence from the climb chart>
- Closest GMs: <top 3 with interval and P(top3)>
- Validation: top-5 identification @ 100 games = <x>% vs chance <y>% → <PASS/FAIL> (bar 30%, fixed in advance).
  Opening ablation: <adjusted vs raw>. Most informative features: <top 3 from importance>.

## Limitations
- Opponent baseline shares interactive features (trades, game length) with the player.
- Untestable assumption: "unusual for your level" means the same at 1800 and GM level.
- Material-blunder detection only sees immediate material loss; positional mistakes are invisible.
- GM rapid games may be years old.

## Run it
    py -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
    setx STOCKFISH_PATH <path to stockfish.exe>
    CHESS_USERNAME=<you> .venv/Scripts/python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_my_style.ipynb
    .venv/Scripts/python -m pytest
```
Fill every `<…>` from the notebook outputs before committing. No `<` may remain: check with `grep -n "<" README.md` (only the `<path to stockfish.exe>` and `<you>` in "Run it" are allowed).

- [ ] **Step 4: Full check**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all 16 passed.

- [ ] **Step 5: Commit**

```bash
git add notebooks/02_validation.py notebooks/02_validation.ipynb README.md
git commit -m "docs: validation notebook and README write-up

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9 (conditional): learned weighting (approach 2)

**Only if Task 8's verdict is FAIL.** If it is PASS, skip this task and note "approach 2 not needed" in the README.

**Files:**
- Modify: `chessstyle/match.py` (add `fit_lda`, `to_lda`; add `lda=False` to `identify`)
- Modify: `notebooks/02_validation.py` (add one cell), `notebooks/01_my_style.py` (switch matching space), `README.md`
- Test: `tests/test_match.py` (append)

**Interfaces:**
- Produces: `match.fit_lda(z) -> LinearDiscriminantAnalysis`, `match.to_lda(model, rows) -> DataFrame`, `match.identify(..., lda=False)`.

- [ ] **Step 1: Write the failing test** — append to `tests/test_match.py`

```python
def test_identify_with_lda_space():
    assert match.identify(gm_table(), chunk=25, lda=True)["top1"] > 0.9
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_match.py::test_identify_with_lda_space -v`
Expected: FAIL, `TypeError: identify() got an unexpected keyword argument 'lda'`

- [ ] **Step 3: Implement** — in `chessstyle/match.py` add the import and two functions:

```python
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis


def fit_lda(z):
    """LDA fitted to separate GMs; NaN z-scores imputed as 0 (the cohort mean)."""
    return LinearDiscriminantAnalysis().fit(z[FEATURES].fillna(0), z.username)


def to_lda(model, rows):
    return pd.DataFrame(model.transform(rows[FEATURES].fillna(0)), index=rows.index)
```
In `identify`, change the signature to `def identify(gm_games, chunk=100, train_frac=0.5, by_opening=True, shuffle=False, drop=None, lda=False, seed=0):` and replace the line `X = z[FEATURES]` with:
```python
    X = to_lda(fit_lda(z[train]), z) if lda else z[FEATURES]
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all 17 passed.

- [ ] **Step 5: Re-validate**: append this cell to `notebooks/02_validation.py`, rebuild and re-execute as in Task 8 Step 2:

```python
# %% 5. Approach 2: LDA-weighted space
lda = match.identify(gm, 100, lda=True)
print(lda, "PASS" if lda["top5"] >= 0.30 else "FAIL")
```

- [ ] **Step 6: If LDA passes, switch notebook 01 to it**: in `notebooks/01_my_style.py`, replace the GM-matches cell's first two lines and the stability cell's vectors with the LDA space:

```python
gm = pd.read_csv(fetch.DATA / "gm_games.csv")
gz = profile.normalise(gm, gm.username.notna())
model = match.fit_lda(gz)
P = match.to_lda(model, gz).groupby(gz.username).mean()
me_l = match.to_lda(model, me)
vec = me_l.mean()
boot = match.bootstrap(me_l.set_axis(profile.FEATURES[:me_l.shape[1]], axis=1), P.set_axis(profile.FEATURES[:P.shape[1]], axis=1))
```
(The `set_axis` relabels the LDA dimensions so `bootstrap`, which indexes `FEATURES`, works unchanged; `explain` now reports discriminant axes, so drop the "shared/differs" text from the print and say so in the README.) Rebuild and re-execute notebook 01 as in Task 7 Step 3.

- [ ] **Step 7: Update the README Results section** with both the approach 1 and approach 2 numbers. If both fail, report that honestly as the finding.

- [ ] **Step 8: Commit**

```bash
git add chessstyle/match.py tests/test_match.py notebooks README.md
git commit -m "feat: LDA-weighted matching (approach 2) after failed validation bar

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
