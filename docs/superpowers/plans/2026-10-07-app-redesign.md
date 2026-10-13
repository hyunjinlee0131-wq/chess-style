# App Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle the Streamlit app as a classic-tournament-hall chess page with plain-language results, GM profile cards (photo, name, openings) and a results-aware reading list.

**Architecture:** A one-off script bakes GM profile details and per-game results into committed CSVs. `present.py` (pure, no Streamlit) turns numbers into plain words, board images and HTML snippets. `app.py`'s `report()` gains the GM details; the page renders `present.py` HTML with a `style.css` theme.

**Tech Stack:** Python 3.13, Streamlit 1.65, pandas, python-chess (`chess.svg`), matplotlib.

**Spec:** `docs/superpowers/specs/2026-10-07-app-redesign-design.md`

## Global Constraints

- **No statistical notation** on the page: no "σ", "z-score", "standard deviation", "bootstrap", "similarity".
- Scale words: `|z| < 0.15` typical; `0.15 ≤ |z| < 0.45` a bit more/less; `|z| ≥ 0.45` much more/less. Labels: `much less · a bit less · typical · a bit more · much more`.
- Match wording: `max(0, round(sim*100))% style match`; `likely LO–HI%` (each clamped at 0); `in the top 3 in K of 10 reshuffles of your games` with `K = round(p_top*10)`.
- Group labels: Aggression, King safety, Simplifying, Piece choices, Clock use.
- 1 large GM card (#1) + 3 small cards (#2–#4) → `report()` returns 4 matches.
- Reading list rows: date, opening, opponent, result (Won/Lost/Draw), link.
- Repo is private: **no repo link** on the page.
- Colours: ivory `#f6efe2`, paper `#fbf7ef`, walnut `#5b3a21`, walnut-2 `#8b5a2b`, board light `#f0d9b5`, board dark `#b58863`, ink `#2b1d12`, muted `#7a6552`, gold `#b8862f`. Fonts: Playfair Display (headings), Source Serif 4 (body).
- All text from chess.com (GM names, opponent usernames, URLs) is HTML-escaped before rendering.
- Python via `.venv/Scripts/python`; full suite: `STOCKFISH_PATH="D:/Projects/chess-style/Tools/stockfish/stockfish-windows-x86-64-universal.exe" .venv/Scripts/python -m pytest -q`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- A GM name or opponent username containing `<`/`&` → shown literally, not as HTML (Task 4 test `test_html_escapes_chess_com_text`).
- A GM missing from `gm_info.csv` → username as name and a piece placeholder instead of a photo (Task 3 test `test_gm_without_profile_falls_back_to_username`; Task 4 test `test_photo_placeholder_without_avatar`).
- Player whose top opening is `other` (e.g. 1.b3) → placeholder instead of a board, no crash (Task 2 test `test_openings_and_boards`; Task 4 test `test_opening_html_without_board`).
- Stockfish missing → engine features NaN → "not available" everywhere, no crash (Task 2 `test_scale_step` NaN case; Task 4 `test_numbers_table_handles_missing`).
- Closest GM has no games in the player's openings → reading section hidden, not an empty table (Task 3 test `test_reading_rows_empty_when_no_games_in_openings`).

---

### Task 1: GM details + game results data

**Files:**
- Create: `scripts/build_gm_info.py`, `tests/test_build_gm_info.py`
- Create (output, committed): `data/gm_info.csv`, `data/gm_results.csv`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `data/gm_info.csv` columns `username,name,title,avatar,country` (one row per GM in `gm_games.csv`; `country` is a 2-letter code like `IN`). `data/gm_results.csv` columns `game,username,opponent,result` (`result` ∈ `win|loss|draw` from `username`'s side).

- [ ] **Step 1: Write the failing test** — `tests/test_build_gm_info.py`

```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_gm_info", Path(__file__).resolve().parent.parent / "scripts" / "build_gm_info.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def game(white_result, black_result):
    return {"white": {"username": "Alice", "result": white_result},
            "black": {"username": "bob", "result": black_result}}


def test_gm_result_from_either_side():
    assert mod.gm_result(game("win", "resigned"), "alice") == ("bob", "win")
    assert mod.gm_result(game("win", "resigned"), "BOB") == ("Alice", "loss")
    assert mod.gm_result(game("agreed", "agreed"), "bob") == ("Alice", "draw")
    assert mod.gm_result(game("timeout", "win"), "alice") == ("bob", "loss")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_build_gm_info.py -v`
Expected: FAIL (`FileNotFoundError` / no such file `scripts/build_gm_info.py`).

- [ ] **Step 3: Implement** — `scripts/build_gm_info.py`

```python
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
```

Append to `.gitignore` (after `!data/gm_games.csv`):

```
!data/gm_info.csv
!data/gm_results.csv
```

- [ ] **Step 4: Run test to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_build_gm_info.py -v`
Expected: 1 passed.

- [ ] **Step 5: Run the script and sanity-check**

Run: `.venv/Scripts/python scripts/build_gm_info.py`
Expected: prints `48 GMs; N of 19036 GM games with results` with N ≥ 18,500 (a few archives may have been refetched since; anything ≥ 97% is fine — report the exact number).
Then: `.venv/Scripts/python -c "import pandas as pd; i=pd.read_csv('data/gm_info.csv', keep_default_na=False); print(i.head(3).to_string()); print((i.avatar=='').sum(), 'without avatar'); r=pd.read_csv('data/gm_results.csv'); print(r.result.value_counts().to_dict())"`
Expected: real names (e.g. `Vidit Gujrathi`), avatar URLs starting `https://`, results split across win/loss/draw.

- [ ] **Step 6: Full suite, then commit**

Run the full suite (Global Constraints). Expected: 29 passed.

```bash
git add scripts/build_gm_info.py tests/test_build_gm_info.py data/gm_info.csv data/gm_results.csv .gitignore
git commit -m "feat: GM profile details and per-game results for the app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `present.py` — plain words, openings, boards

**Files:**
- Create: `present.py` (repo root, next to `app.py`), `tests/test_present.py`

**Interfaces:**
- Consumes: `chessstyle.profile.GROUPS`, `profile.FEATURES`, `profile.INTERACTIVE`.
- Produces (used by Tasks 3–4): `SCALE` (list of 5 str), `LABELS` (group key → label), `GLYPHS` (group key → glyph), `PHRASES` (feature → (more, less)), `FEATURE_NAMES` (feature → short label), `OPENINGS` (family → (name, moves)), `RESULT` (result → Won/Lost/Draw), `scale_step(z) -> int | None`, `habit(feature, z) -> str`, `trait_cards(groups: Series, vec: Series) -> list[dict]` (keys `group, label, glyph, step, summary, habits`), `match_words(m) -> dict` (keys `pct, range, top3`), `shared_sentence(features, vec) -> str`, `differs_sentence(feature | None, vec) -> str`, `blunder_words(you, peers) -> str`, `opening_name(family) -> str`, `board_uri(family, side) -> str | None`, `flag(code) -> str`.

- [ ] **Step 1: Write the failing tests** — `tests/test_present.py`

```python
import pandas as pd
import pytest

import present
from chessstyle import fetch, profile


@pytest.mark.parametrize("z,step", [(0, 2), (0.149, 2), (0.15, 3), (0.449, 3), (0.45, 4), (-0.15, 1),
                                    (-0.449, 1), (-0.45, 0), (-2, 0), (float("nan"), None), (None, None)])
def test_scale_step(z, step):
    assert present.scale_step(z) == step


def test_every_feature_and_group_has_plain_words():
    assert set(present.PHRASES) == set(profile.FEATURES) == set(present.FEATURE_NAMES)
    assert set(present.LABELS) == set(profile.GROUPS) == set(present.GLYPHS)
    assert list(present.LABELS.values()) == ["Aggression", "King safety", "Simplifying", "Piece choices", "Clock use"]


def test_habit_sentence_reads_plainly():
    assert present.habit("time_mid", 0.86) == "You spend more of your clock in the middlegame than most players at your rating."
    assert present.habit("castle_move", -0.4) == "You castle earlier than most players at your rating."
    assert present.habit("game_len", 0.5).endswith("(your opponents affect this too)")


def test_trait_cards():
    vec = pd.Series(0.0, index=profile.FEATURES)
    vec[["time_mid", "time_trouble", "time_end"]] = [0.86, 0.77, -0.17]
    groups = pd.Series({g: vec[fs].mean() for g, fs in profile.GROUPS.items()})
    cards = present.trait_cards(groups, vec)
    assert [c["group"] for c in cards] == list(profile.GROUPS)
    clock = cards[-1]
    assert clock["label"] == "Clock use" and clock["step"] == 3 and clock["glyph"] == present.GLYPHS["Time use"]
    assert clock["summary"] == "A bit more than most players at your rating"
    assert len(clock["habits"]) == 3 and clock["habits"][0].startswith("You spend more of your clock in the middlegame")
    assert cards[0]["habits"] == [] and cards[0]["summary"] == "About typical for your rating"


def test_trait_card_with_no_data():
    vec = pd.Series(float("nan"), index=profile.FEATURES)
    groups = pd.Series({g: float("nan") for g in profile.GROUPS})
    card = present.trait_cards(groups, vec)[0]
    assert card["step"] is None and card["summary"] == "Not enough data" and card["habits"] == []


def test_match_words():
    assert present.match_words({"sim": 0.8, "lo": 0.734, "hi": 0.86, "p_top": 0.81}) == {
        "pct": "80% style match", "range": "likely 73–86%", "top3": "in the top 3 in 8 of 10 reshuffles of your games"}
    assert present.match_words({"sim": -0.2, "lo": -0.3, "hi": 0.1, "p_top": 0.0})["pct"] == "0% style match"


def test_shared_and_differs():
    vec = pd.Series({"time_mid": 0.9, "castled": 0.4, "checks": -0.3, "pawn_storm": -0.5})
    assert present.shared_sentence(["time_mid", "checks"], vec) == \
        "you both spend more of your clock in the middlegame and give fewer checks"
    assert present.shared_sentence(["time_mid", "castled", "checks"], vec) == (
        "you both spend more of your clock in the middlegame, castle in more of your games and give fewer checks")
    assert present.shared_sentence([], vec) == ""
    assert present.differs_sentence("pawn_storm", vec) == \
        "you push pawns at the enemy king less often; they tend the other way"
    assert present.differs_sentence(None, vec) == ""


def test_blunder_words():
    assert present.blunder_words(0.59, 0.51) == "a bit more often than"
    assert present.blunder_words(0.5, 0.5) == "about as often as"
    assert present.blunder_words(0.2, 0.5) == "much less often than"
    assert present.blunder_words(float("nan"), 0.5) == "not available"


def test_openings_and_boards():
    fams = set(pd.read_csv(fetch.DATA / "gm_games.csv").family)
    assert fams <= set(present.OPENINGS)
    assert present.opening_name("french") == "French Defence"
    assert present.opening_name("made-up") == "made-up"
    assert present.board_uri("french", "black").startswith("data:image/svg+xml;base64,")
    assert present.board_uri("other", "white") is None


def test_flag():
    assert present.flag("IN") == "🇮🇳"
    assert present.flag("") == "" and present.flag("XXX") == "" and present.flag("12") == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_present.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'present'`.

- [ ] **Step 3: Implement** — `present.py`

```python
"""Plain-language wording and chess visuals for the app. No Streamlit here, so it is unit-testable."""
import base64
import math

import chess
import chess.svg

from chessstyle import profile

SCALE = ["much less", "a bit less", "typical", "a bit more", "much more"]
LABELS = {"Aggression": "Aggression", "King play": "King safety", "Simplification": "Simplifying",
          "Piece preference": "Piece choices", "Time use": "Clock use"}
GLYPHS = {"Aggression": "♞", "King play": "♚", "Simplification": "♛", "Piece preference": "♝", "Time use": "♜"}
PHRASES = {
    "checks": ("give more checks", "give fewer checks"),
    "captures": ("capture more often", "capture less often"),
    "sacrifices": ("sacrifice material more often", "sacrifice material less often"),
    "early_queen": ("bring your queen out early more often", "bring your queen out early less often"),
    "castled": ("castle in more of your games", "castle in fewer of your games"),
    "castle_move": ("castle later", "castle earlier"),
    "castle_long": ("castle queenside more often", "castle queenside less often"),
    "opposite_castle": ("end up with kings on opposite sides more often", "end up with kings on opposite sides less often"),
    "pawn_storm": ("push pawns at the enemy king more often", "push pawns at the enemy king less often"),
    "queen_trade": ("trade queens more often", "trade queens less often"),
    "queen_trade_move": ("trade queens later", "trade queens earlier"),
    "material_30": ("keep more pieces on the board by move 30", "have fewer pieces left by move 30"),
    "endgame": ("reach endgames more often", "reach endgames less often"),
    "game_len": ("play longer games", "play shorter games"),
    "bishop_takes_knight": ("swap bishops for knights more often", "swap bishops for knights less often"),
    "bishop_pair_kept": ("keep both bishops more often", "keep both bishops less often"),
    "pawn_share": ("move pawns more", "move pawns less"),
    "time_open": ("spend more of your clock in the opening", "spend less of your clock in the opening"),
    "time_mid": ("spend more of your clock in the middlegame", "spend less of your clock in the middlegame"),
    "time_end": ("spend more of your clock in the endgame", "spend less of your clock in the endgame"),
    "time_trouble": ("get into time trouble more often", "get into time trouble less often"),
}
FEATURE_NAMES = {
    "checks": "Checks per move", "captures": "Captures per move", "sacrifices": "Sacrifices per game",
    "early_queen": "Queen out before move 8", "castled": "Castled", "castle_move": "Move you castled on",
    "castle_long": "Castled queenside", "opposite_castle": "Kings on opposite sides",
    "pawn_storm": "Pawn pushes at the enemy king", "queen_trade": "Queens traded",
    "queen_trade_move": "Move queens were traded", "material_30": "Material left at move 30",
    "endgame": "Reached an endgame", "game_len": "Game length (moves)",
    "bishop_takes_knight": "Bishop-for-knight swaps", "bishop_pair_kept": "Kept both bishops (move 20)",
    "pawn_share": "Share of moves that are pawn moves", "time_open": "Clock used in the opening",
    "time_mid": "Clock used in the middlegame", "time_end": "Clock used in the endgame",
    "time_trouble": "Got into time trouble",
}
OPENINGS = {
    "sicilian": ("Sicilian Defence", "1.e4 c5"), "open": ("Open Game", "1.e4 e5"),
    "french": ("French Defence", "1.e4 e6"), "caro-kann": ("Caro-Kann Defence", "1.e4 c6"),
    "scandinavian": ("Scandinavian Defence", "1.e4 d5"), "e4-other": ("Other replies to 1.e4", "1.e4"),
    "closed": ("Closed Game", "1.d4 d5"), "indian": ("Indian Defence", "1.d4 Nf6"),
    "d4-other": ("Other replies to 1.d4", "1.d4"), "english": ("English Opening", "1.c4"),
    "reti": ("Réti Opening", "1.Nf3"), "other": ("Other first moves", ""),
}
RESULT = {"win": "Won", "loss": "Lost", "draw": "Draw"}
THAN = " than most players at your rating"


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def scale_step(z):
    """Index into SCALE (0 = much less … 4 = much more); None when there is no value."""
    if _missing(z):
        return None
    a = abs(z)
    if a < 0.15:
        return 2
    return 2 + (1 if a < 0.45 else 2) * (1 if z > 0 else -1)


def _phrase(feature, z):
    return PHRASES[feature][0 if z > 0 else 1]


def habit(feature, z):
    note = " (your opponents affect this too)" if feature in profile.INTERACTIVE else ""
    return f"You {_phrase(feature, z)}{THAN}.{note}"


def trait_cards(groups, vec):
    """One card per style group: label, glyph, scale step, summary sentence, up to 3 distinctive habits."""
    cards = []
    for g, fs in profile.GROUPS.items():
        step = scale_step(groups[g])
        summary = ("Not enough data" if step is None else "About typical for your rating" if step == 2
                   else SCALE[step].capitalize() + THAN)
        strong = sorted((f for f in fs if not _missing(vec[f]) and abs(vec[f]) >= 0.15), key=lambda f: -abs(vec[f]))
        cards.append({"group": g, "label": LABELS[g], "glyph": GLYPHS[g], "step": step, "summary": summary,
                      "habits": [habit(f, vec[f]) for f in strong[:3]]})
    return cards


def _pct(x):
    return max(0, round(x * 100))


def match_words(m):
    return {"pct": f"{_pct(m['sim'])}% style match", "range": f"likely {_pct(m['lo'])}–{_pct(m['hi'])}%",
            "top3": f"in the top 3 in {round(m['p_top'] * 10)} of 10 reshuffles of your games"}


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def shared_sentence(features, vec):
    parts = [_phrase(f, vec[f]) for f in features if f in vec and not _missing(vec[f])]
    return "you both " + _join(parts) if parts else ""


def differs_sentence(feature, vec):
    if feature is None or feature not in vec or _missing(vec[feature]):
        return ""
    return f"you {_phrase(feature, vec[feature])}; they tend the other way"


def blunder_words(you, peers):
    if _missing(you) or _missing(peers):
        return "not available"
    d = (you - peers) / peers if peers else 0.0
    if abs(d) < 0.1:
        return "about as often as"
    return f"{'a bit' if abs(d) < 0.3 else 'much'} {'more' if d > 0 else 'less'} often than"


def opening_name(family):
    return OPENINGS.get(family, (family, ""))[0]


BOARD_COLORS = {"square light": "#f0d9b5", "square dark": "#b58863", "margin": "#5b3a21"}


def board_uri(family, side, size=200):
    """Opening position as a base64 SVG data URI (walnut/ivory squares), or None when there is no fixed position."""
    moves = OPENINGS.get(family, ("", ""))[1]
    if not moves:
        return None
    board = chess.Board()
    for tok in moves.split():
        board.push_san(tok.split(".")[-1])
    svg = chess.svg.board(board, orientation=chess.WHITE if side == "white" else chess.BLACK, size=size,
                          coordinates=False, colors=BOARD_COLORS)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def flag(code):
    """Two-letter country code -> flag emoji ('' if not a plain two-letter code)."""
    code = (code or "").upper()
    if len(code) != 2 or not code.isalpha():
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_present.py -v`
Expected: all pass.

- [ ] **Step 5: Full suite, then commit**

Run the full suite. Expected: all passed.

```bash
git add present.py tests/test_present.py
git commit -m "feat: plain-language wording, opening names and board images for the app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `report()` with GM details, openings and reading rows

**Files:**
- Modify: `app.py` (`gm_profiles`, `report`, `analyse`, three page lines that read changed keys)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `data/gm_info.csv`, `data/gm_results.csv` (Task 1); `match.bootstrap`, `match.explain`, `match.reading_list`.
- Produces (used by Task 4):
  - `gm_profiles() -> (gm, P, info)`: `gm` = `gm_games.csv` left-merged with `gm_results.csv` on `[game, username]` (adds `opponent`, `result`); `P` = GM style vectors; `info` = `gm_info.csv` indexed by `username` (blanks are `""`).
  - `report(table, gm, P, info) -> dict` keys: `games`, `ratings`, `groups`, `features` (player z Series), `raw` (player mean raw features), `peer_raw` (peer mean raw features), `openings` (list of ≤3 `{family, side, share}`), `blunders` (you, peers), `matches` (4 dicts: `user, sim, lo, hi, p_top, shared, differs, name, title, avatar, country, openings`), `reading` (list of `{url, date, family, side, opponent, result}`; `date` is `YYYY-MM-DD`; `result` ∈ `win|loss|draw|""`).
  - `top_openings(rows, n=3)`, `reading_rows(gm, user, fams)`.

- [ ] **Step 1: Update the tests** — in `tests/test_app.py` replace `test_report_has_everything_the_page_shows` and `test_report_empty_table_is_a_clear_error`, and add three tests:

```python
def test_report_has_everything_the_page_shows():
    gm, P, info = app.gm_profiles()
    r = app.report(fake_table(), gm, P, info)
    assert set(r) == {"games", "ratings", "groups", "features", "raw", "peer_raw", "openings", "blunders",
                      "matches", "reading"}
    assert list(r["groups"].index) == list(profile.GROUPS)
    assert len(r["matches"]) == 4
    assert [m["sim"] for m in r["matches"]] == sorted((m["sim"] for m in r["matches"]), reverse=True)
    m = r["matches"][0]
    assert {"user", "sim", "lo", "hi", "p_top", "shared", "differs", "name", "title", "avatar", "country",
            "openings"} <= set(m)
    assert m["name"] and m["openings"] and set(m["openings"][0]) == {"family", "side", "share"}
    assert 1 <= len(r["openings"]) <= 3 and set(r["openings"][0]) == {"family", "side", "share"}
    assert set(r["raw"].index) == set(profile.FEATURES)
    assert r["reading"] and set(r["reading"][0]) == {"url", "date", "family", "side", "opponent", "result"}
    assert all(x["url"].startswith("https://") and len(x["date"]) == 10 for x in r["reading"])
    assert {x["result"] for x in r["reading"]} <= {"win", "loss", "draw", ""}


def test_report_empty_table_is_a_clear_error():
    gm, P, info = app.gm_profiles()
    with pytest.raises(ValueError, match="no rated rapid games"):
        app.report(pd.DataFrame(), gm, P, info)


def test_gm_without_profile_falls_back_to_username():
    gm, P, info = app.gm_profiles()
    m = app.report(fake_table(), gm, P, info.iloc[0:0])["matches"][0]
    assert m["name"] == m["user"] and m["avatar"] == "" and m["title"] == ""


def test_reading_rows_empty_when_no_games_in_openings():
    gm, _, _ = app.gm_profiles()
    assert app.reading_rows(gm, gm.username.iloc[0], ["no-such-family|white"]) == []


def test_gm_results_are_merged():
    gm, _, _ = app.gm_profiles()
    assert {"opponent", "result"} <= set(gm.columns)
    assert gm.result.notna().mean() > 0.95
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -v`
Expected: FAIL — `ValueError: not enough values to unpack (expected 3, got 2)` (or similar).

- [ ] **Step 3: Implement** — in `app.py`, replace `gm_profiles`, `report` and `analyse` with:

```python
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
```

Keep the existing page working with the new shapes (Task 4 replaces it entirely):
- `len(gm_profiles()[1])` stays as is (index 1 is still `P`).
- Replace `left.dataframe(r["openings"].rename("share").map("{:.0%}".format))` with
  `left.dataframe(pd.DataFrame(r["openings"]))`.
- Replace the reading loop `for url in r["reading"]: st.markdown(f"- {url}")` with
  `for x in r["reading"]: st.markdown(f"- {x['date']} · {x['result']} · {x['url']}")`.

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -v`
Expected: 5 passed.

- [ ] **Step 5: Full suite, then commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: report carries GM details, top openings and reading rows with results

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Chess-themed page

**Files:**
- Modify: `present.py` (append HTML builders, radar, numbers table), `app.py` (replace the page block, drop `REPO`)
- Create: `style.css`, `.streamlit/config.toml`
- Test: `tests/test_present.py` (append)

**Interfaces:**
- Consumes: everything Task 2 produced; `report()` dict shape from Task 3.
- Produces: `section_html(glyph, title, sub="")`, `trait_card_html(card)`, `photo_html(m)`, `gm_hero_html(m, vec)`, `gm_small_html(m, vec, rank)`, `opening_html(o)`, `reading_table_html(rows)`, `numbers_table(r) -> DataFrame`, `radar(cards) -> matplotlib Figure` — all in `present.py`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_present.py`

```python
def gm_match(**kw):
    m = {"user": "someone", "sim": 0.8, "lo": 0.7, "hi": 0.9, "p_top": 0.8, "shared": ["time_mid"],
         "differs": "pawn_storm", "name": "Some One", "title": "GM", "avatar": "https://img/x.png", "country": "IN",
         "openings": [{"family": "french", "side": "black", "share": 0.4}]}
    return {**m, **kw}


VEC = pd.Series({f: 0.0 for f in profile.FEATURES} | {"time_mid": 0.9, "pawn_storm": -0.5})


def test_html_escapes_chess_com_text():
    html = present.gm_hero_html(gm_match(name="<b>x</b> & co"), VEC)
    assert "&lt;b&gt;x&lt;/b&gt; &amp; co" in html and "<b>x</b>" not in html
    rows = [{"url": "https://www.chess.com/game/live/1", "date": "2026-01-02", "family": "french", "side": "black",
             "opponent": "<script>", "result": "win"}]
    table = present.reading_table_html(rows)
    assert "&lt;script&gt;" in table and "Won" in table and "French Defence" in table


def test_gm_cards_use_plain_words():
    hero = present.gm_hero_html(gm_match(), VEC)
    assert "80% style match" in hero and "likely 70–90%" in hero and "🇮🇳" in hero and "French Defence" in hero
    assert "you both spend more of your clock in the middlegame" in hero
    assert "https://www.chess.com/member/someone" in hero
    small = present.gm_small_html(gm_match(), VEC, 2)
    assert "#2" in small and "80% style match" in small
    for html in (hero, small):
        assert "σ" not in html and "similarity" not in html.lower()


def test_photo_placeholder_without_avatar():
    assert "<img" not in present.photo_html(gm_match(avatar=""))
    assert '<img src="https://img/x.png"' in present.photo_html(gm_match())


def test_opening_html_without_board():
    assert "<img" not in present.opening_html({"family": "other", "side": "white", "share": 0.2})
    assert "data:image/svg+xml;base64," in present.opening_html({"family": "french", "side": "black", "share": 0.3})


def test_trait_card_html_marks_the_step():
    card = {"group": "Time use", "label": "Clock use", "glyph": "♜", "step": 4, "summary": "Much more than most",
            "habits": ["You get into time trouble more often than most players at your rating."]}
    html = present.trait_card_html(card)
    assert html.count('class="on"') == 1 and "Clock use" in html and "<li>" in html


def test_numbers_table_handles_missing():
    r = {"features": VEC.copy(), "raw": pd.Series(0.1, index=profile.FEATURES),
         "peer_raw": pd.Series(0.1, index=profile.FEATURES)}
    r["features"]["sacrifices"] = float("nan")
    r["raw"]["sacrifices"] = float("nan")
    t = present.numbers_table(r)
    assert len(t) == len(profile.FEATURES)
    row = t[t.Habit == "Sacrifices per game"].iloc[0]
    assert row["Compared with them"] == "not available" and row["You"] == "—"
    assert "σ" not in t.to_string()


def test_radar_returns_a_figure():
    cards = present.trait_cards(pd.Series({g: 0.3 for g in profile.GROUPS}), VEC)
    fig = present.radar(cards)
    assert fig.axes and fig.axes[0].name == "polar"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_present.py -v`
Expected: the new tests FAIL with `AttributeError: module 'present' has no attribute 'gm_hero_html'` (etc.).

- [ ] **Step 3: Append to `present.py`** (add `from html import escape as esc`, `import matplotlib`, `matplotlib.use("Agg")`, `import matplotlib.pyplot as plt`, `import numpy as np`, `import pandas as pd` to the imports at the top)

```python
def section_html(glyph, title, sub=""):
    return (f'<div class="cs-section"><span class="glyph">{glyph}</span><h2>{esc(title)}</h2>'
            f'<span class="sub">{esc(sub)}</span></div>')


def _scale_html(step):
    cells = "".join(f'<div class="{"on" if i == step else ""}"></div>' for i in range(5))
    labels = "".join(f"<span>{s}</span>" for s in SCALE)
    return f'<div class="cs-scale">{cells}</div><div class="cs-scale-labels">{labels}</div>'


def trait_card_html(c):
    habits = "".join(f"<li>{esc(h)}</li>" for h in c["habits"])
    return (f'<div class="cs-card"><h4>{c["glyph"]} {esc(c["label"])}</h4>{_scale_html(c["step"])}'
            f'<div class="summary">{esc(c["summary"])}</div>' + (f"<ul>{habits}</ul>" if habits else "") + "</div>")


def photo_html(m):
    if str(m.get("avatar", "")).startswith("https://"):
        return f'<img src="{esc(m["avatar"])}" alt="{esc(m["name"])}">'
    return '<div class="placeholder">♚</div>'


def _title(m):
    return f'<span class="cs-title-badge">{esc(m["title"])}</span>' if m.get("title") else ""


def gm_hero_html(m, vec):
    w = match_words(m)
    ops = ", ".join(f'{opening_name(o["family"])} as {o["side"]} ({o["share"]:.0%})' for o in m["openings"])
    shared, differs = shared_sentence(m["shared"], vec), differs_sentence(m["differs"], vec)
    return (f'<div class="cs-card cs-gm">{photo_html(m)}<div>'
            f'<p class="name">{_title(m)}{esc(m["name"])} {flag(m["country"])}</p>'
            f'<div><span class="cs-pct">{w["pct"]}</span> <span class="cs-muted">{w["range"]} · {w["top3"]}</span></div>'
            + (f'<p><b>Plays like you because</b> {esc(shared)}.</p>' if shared else "")
            + (f'<p><b>Where you differ:</b> {esc(differs)}.</p>' if differs else "")
            + (f'<p><b>Favourite openings:</b> {esc(ops)}</p>' if ops else "")
            + f'<p><a href="https://www.chess.com/member/{esc(m["user"])}" target="_blank">'
              f'View {esc(m["name"])} on chess.com →</a></p></div></div>')


def gm_small_html(m, vec, rank):
    w = match_words(m)
    because = shared_sentence(m["shared"][:1], vec)
    return (f'<div class="cs-card cs-small">{photo_html(m)}<div class="cs-muted">#{rank}</div>'
            f'<h4>{_title(m)}{esc(m["name"])} {flag(m["country"])}</h4>'
            f'<div class="cs-pct cs-pct-small">{w["pct"]}</div>'
            f'<div class="cs-muted">{esc(because[:1].upper() + because[1:])}</div></div>')


def opening_html(o):
    name, moves = OPENINGS.get(o["family"], (o["family"], ""))
    uri = board_uri(o["family"], o["side"])
    img = f'<img src="{uri}" alt="{esc(name)}">' if uri else '<div class="placeholder">♟</div>'
    detail = " · ".join(x for x in (moves, f"as {o['side']}", f"{o['share']:.0%} of your games") if x)
    return f'<div class="cs-card cs-opening">{img}<h4>{esc(name)}</h4><div class="cs-muted">{esc(detail)}</div></div>'


def reading_table_html(rows):
    body = "".join(
        f'<tr><td>{esc(r["date"])}</td><td>{esc(opening_name(r["family"]))} '
        f'<span class="cs-muted">as {esc(r["side"])}</span></td><td>{esc(r["opponent"])}</td>'
        f'<td class="cs-{esc(r["result"] or "draw")}">{RESULT.get(r["result"], "—")}</td>'
        f'<td><a href="{esc(r["url"])}" target="_blank">Open game →</a></td></tr>' for r in rows)
    return ('<table class="cs-table"><tr><th>Date</th><th>Opening</th><th>Opponent</th><th>Result</th><th></th></tr>'
            f"{body}</table>")


def _num(x):
    return "—" if _missing(x) else f"{x:.2f}"


def numbers_table(r):
    rows = []
    for g, fs in profile.GROUPS.items():
        for f in fs:
            s = scale_step(r["features"][f])
            rows.append({"Area": LABELS[g], "Habit": FEATURE_NAMES[f], "You": _num(r["raw"][f]),
                         "Players at your rating": _num(r["peer_raw"][f]),
                         "Compared with them": "not available" if s is None else SCALE[s]})
    return pd.DataFrame(rows)


def radar(cards):
    """Five style groups on the 5-step scale; dashed ring = typical."""
    labels = [c["label"] for c in cards]
    vals = [2 if c["step"] is None else c["step"] for c in cards]
    ang = np.linspace(0, 2 * np.pi, len(cards), endpoint=False).tolist()
    loop = lambda xs: xs + xs[:1]
    fig, ax = plt.subplots(figsize=(4.2, 4.2), subplot_kw={"polar": True})
    fig.patch.set_facecolor("#f6efe2")
    ax.set_facecolor("#fbf7ef")
    ax.plot(loop(ang), [2] * (len(ang) + 1), color="#b58863", lw=1, ls="--")
    ax.plot(loop(ang), loop(vals), color="#5b3a21", lw=2.2)
    ax.fill(loop(ang), loop(vals), color="#8b5a2b", alpha=0.25)
    ax.set_ylim(0, 4)
    ax.set_yticks([0, 2, 4], ["much less", "typical", "much more"], color="#7a6552", fontsize=7)
    ax.set_xticks(ang, labels, fontfamily="serif", color="#2b1d12", fontsize=10)
    ax.spines["polar"].set_color("#b58863")
    ax.grid(color="#e3d5bd")
    return fig
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_present.py -v`
Expected: all pass.

- [ ] **Step 5: Create `style.css`** (repo root)

```css
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=Source+Serif+4:wght@400;600&display=swap');
:root { --ivory:#f6efe2; --paper:#fbf7ef; --walnut:#5b3a21; --walnut-2:#8b5a2b; --sq-light:#f0d9b5;
        --sq-dark:#b58863; --ink:#2b1d12; --muted:#7a6552; --gold:#b8862f; --line:#e3d5bd; }
html, body, .stApp, .stMarkdown, .stTextInput input, button { font-family: 'Source Serif 4', Georgia, serif; color: var(--ink); }
.stApp { background: var(--ivory) repeating-conic-gradient(rgba(91,58,33,.035) 0 25%, transparent 0 50%) 0 0 / 64px 64px; }
h1, h2, h3, h4 { font-family: 'Playfair Display', Georgia, serif; color: var(--walnut); }
.block-container { max-width: 1100px; }
.cs-hero { text-align: center; padding: 1.5rem 1rem .5rem; }
.cs-hero .glyph { font-size: 3.4rem; color: var(--walnut); line-height: 1; }
.cs-hero h1 { font-size: 2.6rem; margin: .3rem 0; }
.cs-hero p { color: var(--muted); font-size: 1.1rem; max-width: 660px; margin: 0 auto; }
.cs-section { display: flex; align-items: baseline; gap: .6rem; border-bottom: 2px solid var(--walnut); margin: 2.2rem 0 1rem; padding-bottom: .3rem; }
.cs-section .glyph { font-size: 1.8rem; color: var(--walnut-2); }
.cs-section h2 { margin: 0; padding: 0; font-size: 1.7rem; }
.cs-section .sub { color: var(--muted); margin-left: auto; font-size: .95rem; }
.cs-card { background: var(--paper); border: 1px solid var(--line); border-left: 6px solid var(--walnut-2); border-radius: 10px; padding: .9rem 1.1rem; margin-bottom: .8rem; box-shadow: 0 1px 3px rgba(43,29,18,.08); }
.cs-card h4 { margin: 0 0 .3rem; padding: 0; font-size: 1.15rem; }
.cs-card .summary { color: var(--muted); margin: .2rem 0 .4rem; }
.cs-card ul { margin: .2rem 0 0 1.1rem; padding: 0; }
.cs-card li { margin: .15rem 0; }
.cs-scale { display: grid; grid-template-columns: repeat(5, 1fr); gap: 3px; margin: .4rem 0 .1rem; }
.cs-scale div { height: 14px; border-radius: 3px; background: var(--sq-light); }
.cs-scale div:nth-child(even) { background: #e3c9a0; }
.cs-scale div.on { background: var(--walnut); }
.cs-scale-labels { display: grid; grid-template-columns: repeat(5, 1fr); font-size: .72rem; color: var(--muted); text-align: center; }
.cs-gm { display: flex; gap: 1.3rem; align-items: flex-start; border-left-color: var(--gold); }
.cs-gm img, .cs-gm .placeholder { width: 128px; height: 128px; flex: none; border-radius: 8px; object-fit: cover; border: 3px solid var(--walnut); }
.placeholder { display: flex; align-items: center; justify-content: center; font-size: 4rem; background: var(--sq-light); color: var(--walnut); }
.cs-gm .name { font-family: 'Playfair Display', Georgia, serif; font-size: 1.7rem; color: var(--walnut); margin: 0 0 .2rem; }
.cs-gm p { margin: .35rem 0; }
.cs-title-badge { display: inline-block; background: var(--walnut); color: var(--paper); font-family: 'Source Serif 4', serif; font-weight: 600; font-size: .8rem; padding: .05rem .45rem; border-radius: 4px; margin-right: .45rem; vertical-align: middle; }
.cs-pct { font-size: 2rem; font-family: 'Playfair Display', Georgia, serif; color: var(--walnut-2); }
.cs-pct-small { font-size: 1.4rem; }
.cs-muted { color: var(--muted); }
.cs-small { text-align: center; border-left: 1px solid var(--line); border-top: 6px solid var(--walnut-2); min-height: 260px; }
.cs-small img, .cs-small .placeholder { width: 88px; height: 88px; border-radius: 50%; object-fit: cover; border: 3px solid var(--walnut); margin: 0 auto .4rem; display: block; font-size: 2.6rem; }
.cs-small .placeholder { display: flex; }
.cs-opening { text-align: center; }
.cs-opening img, .cs-opening .placeholder { width: 100%; max-width: 200px; aspect-ratio: 1; border: 4px solid var(--walnut); border-radius: 4px; margin: 0 auto .4rem; }
.cs-table { width: 100%; border-collapse: collapse; background: var(--paper); border-radius: 8px; overflow: hidden; }
.cs-table th { text-align: left; font-family: 'Playfair Display', Georgia, serif; color: var(--walnut); border-bottom: 2px solid var(--walnut); padding: .5rem; }
.cs-table td { padding: .5rem; border-bottom: 1px solid var(--line); }
.cs-table tr:nth-child(even) td { background: #f3e9d6; }
.cs-win { color: #2f6b2f; font-weight: 600; }
.cs-loss { color: #9b2c2c; font-weight: 600; }
.cs-draw { color: var(--muted); font-weight: 600; }
a { color: var(--walnut-2); }
@media (max-width: 640px) {
  .cs-gm { flex-direction: column; align-items: center; text-align: center; }
  .cs-hero h1 { font-size: 1.9rem; }
  .cs-section .sub { display: none; }
}
```

- [ ] **Step 6: Create `.streamlit/config.toml`**

```toml
[theme]
base = "light"
primaryColor = "#8b5a2b"
backgroundColor = "#f6efe2"
secondaryBackgroundColor = "#efe4cf"
textColor = "#2b1d12"
font = "serif"
```

- [ ] **Step 7: Replace the page block in `app.py`**

Add `from pathlib import Path` and `import present` to the imports, delete the `REPO = ...` line, add `EXAMPLE = "tanit0131"` under `N_GAMES`, and replace everything from `if st.runtime.exists():` to the end of the file with:

```python
if st.runtime.exists():
    st.set_page_config(page_title="Which GM plays like you?", page_icon="♞", layout="centered")
    st.markdown(f"<style>{(Path(__file__).parent / 'style.css').read_text(encoding='utf-8')}</style>",
                unsafe_allow_html=True)
    n_gms = len(gm_profiles()[1])
    st.markdown(
        '<div class="cs-hero"><div class="glyph">♞</div><h1>Which grandmaster plays like you?</h1>'
        f"<p>We read your last {N_GAMES} rated rapid games on chess.com, compare your habits with players at your "
        f"rating, and find which of {n_gms} grandmasters and chess personalities play most like you.</p></div>",
        unsafe_allow_html=True)

    with st.form("lookup"):
        username = st.text_input("Your chess.com username", placeholder="e.g. hikaru").strip().lower()
        left, right = st.columns(2)
        go = left.form_submit_button("Find my grandmaster", type="primary", use_container_width=True)
        example = right.form_submit_button(f"Try an example ({EXAMPLE})", use_container_width=True)
    if example:
        username, go = EXAMPLE, True
    if not (go and username):
        st.stop()

    try:
        with st.spinner(f"Reading {username}'s recent games and comparing habits... (about 20 seconds)"):
            r = analyse(username)
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
    left.pyplot(present.radar(cards), use_container_width=True)
    with right:
        for c in cards:
            html(present.trait_card_html(c))

    html(present.section_html("♟", "Your openings", "your most played"))
    for col, o in zip(st.columns(3), r["openings"]):
        with col:
            html(present.opening_html(o))
    you, peers = r["blunders"]
    if not pd.isna(you):
        html(f'<div class="cs-card">You lose material by mistake <b>{present.blunder_words(you, peers)}</b> players '
             f"at your rating ({you:.2f} vs {peers:.2f} times per game).</div>")

    html(present.section_html("♛", "Your closest grandmasters", "who shares your habits"))
    top, *rest = r["matches"]
    html(present.gm_hero_html(top, vec))
    for rank, (col, m) in enumerate(zip(st.columns(3), rest), start=2):
        with col:
            html(present.gm_small_html(m, vec, rank))

    if r["reading"]:
        html(present.section_html("♗", f"Study {top['name']}'s games", "in the openings you play"))
        html(present.reading_table_html(r["reading"]))

    with st.expander("Show the numbers"):
        st.caption("Your average per game next to players at your rating. 'Compared with them' also allows for the "
                   "openings you play, so it can differ slightly from the raw averages.")
        st.dataframe(present.numbers_table(r), hide_index=True, use_container_width=True)
    with st.expander("How does this work?"):
        st.markdown(
            f"1. Each of your games becomes 21 habits: how often you check and capture, when you castle, "
            f"when queens come off, how you spend your clock, and so on.\n"
            f"2. Those habits are compared with your opponents at the same rating, allowing for the openings you "
            f"play, so the result describes style rather than strength or repertoire.\n"
            f"3. The same is done for {n_gms} grandmasters and chess personalities; the closest ones share the most "
            f"habits with you.\n"
            f"4. To show how sure the match is, your games are reshuffled 1,000 times and the matching is redone. "
            f"The 'likely' range and 'top 3 in 8 of 10' come from that.\n\n"
            f"Tested on grandmasters themselves: given 100 of a grandmaster's games, the method puts the right one in "
            f"its top 5 44% of the time (picking at random would manage 10%).")

    html(f'<p class="cs-muted" style="text-align:center;margin-top:2rem">Based on {r["games"]} recent games, '
         f'rating {r["ratings"][0]}–{r["ratings"][1]}.</p>')
```

- [ ] **Step 8: Full suite**

Run the full suite. Expected: all passed.

- [ ] **Step 9: Run the page (AppTest + headless)**

In a throwaway script outside the repo (not committed), with `STOCKFISH_PATH` set:
`from streamlit.testing.v1 import AppTest; at = AppTest.from_file("app.py", default_timeout=240); at.run()`, then
- set `at.text_input[0]` to `" Tanit0131 "` and click the first form submit button, `at.run()`: no exception, no `at.error`, and the markdown contains "Your style", "Your openings", "Your closest grandmasters", "% style match"; no markdown element contains "σ".
- fresh AppTest, click the "Try an example" button: same checks pass.
- fresh AppTest, input `"nobody-xyz-123"`: `at.error[0].value` contains "not found".
Also start `.venv/Scripts/python -m streamlit run app.py --server.headless true --server.port 8502` in the background, confirm `http://localhost:8502/_stcore/health` returns `ok`, then stop it. Paste results into the report.

- [ ] **Step 10: Commit**

```bash
git add present.py app.py style.css .streamlit/config.toml tests/test_present.py
git commit -m "feat: chess-themed page with trait cards, radar, opening boards and GM cards

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
