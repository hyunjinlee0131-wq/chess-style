# Blitz Matching + Quality Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a validated Rapid/Blitz like-for-like switch, a "How well you play" panel (Bad–Excellent), and 5 neutral style levels.

**Architecture:** A one-off script builds a blitz GM pool from cached archives; notebook 02 validates it. `present.py` gains 5-level style wording and quality rows/cards (pure, tested). `app.py` loads the pool per time control and renders the new panel.

**Tech Stack:** Python 3.13, Streamlit 1.65, pandas, python-chess, Stockfish, nbformat/nbclient.

**Spec:** `docs/superpowers/specs/2026-10-08-blitz-and-quality-design.md`

## Global Constraints

- Blitz pool: same accounts as `data/gm_info.csv`; each one's **500** most recent rated blitz games; accounts with **< 200** blitz games left out.
- Validation bar (pre-registered): blitz top-5 @ 100 games **≥ 30%**; shuffled labels at chance. FAIL → app ships rapid-only.
- Style levels by strongest habit `|z|`: `< 0.15` typical · `< 0.30` slightly · `< 0.45` clearly · `< 0.80` strongly · else very strongly distinctive.
- Quality levels by score `(you − peers)/peers_sd` (sign flipped when lower is better): `< −0.3` Bad · `< −0.1` Weak · `< 0.1` Average · `< 0.3` Good · else Excellent.
- Accuracy shown only with **≥ 20** reviewed current games.
- No statistical notation on the page (no σ, z-score, standard deviation, bootstrap, similarity). Style levels never use good/bad words.
- Do not deploy and do not push (deploy is held).
- Python `.venv/Scripts/python`; Stockfish `STOCKFISH_PATH="D:/Projects/chess-style/Tools/stockfish/stockfish-windows-x86-64-universal.exe"`; full suite `STOCKFISH_PATH=... .venv/Scripts/python -m pytest -q`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Player with no blitz (or too few) games picks Blitz → the existing friendly "need at least 100 rated games…" / "no rated blitz games" message, not a crash (Task 3 test `test_report_empty_table_names_time_class`).
- Player with < 20 reviewed games → accuracy row says "Not available — review more…", other rows still rated (Task 3 test `test_quality_rows` few-games case).
- Feature table without an `accuracy` column (old data / GM tables) → accuracy row unavailable, no KeyError (Task 3 test `test_quality_rows_without_accuracy_column`).
- Peers with zero spread on a measure (e.g. nobody in time trouble) → that row unavailable, no division by zero (Task 3 test `test_quality_rows_zero_spread`).
- Same username looked up in both time controls → separate cached results (cache key includes time control; Task 4 AppTest step).

---

### Task 1: Accuracy column + blitz GM pool

**Files:**
- Modify: `chessstyle/features.py` (`features_table` row dict), `chessstyle/fetch.py` (add `result_for`), `scripts/build_gm_info.py` (use `fetch.result_for`), `.gitignore`
- Create: `scripts/build_gm_blitz.py`; outputs `data/gm_blitz.csv`, `data/gm_blitz_results.csv` (committed)
- Test: `tests/test_features.py`, `tests/test_fetch.py`

**Interfaces:**
- Produces: `features_table` rows gain `accuracy` (float, NaN when the game has no chess.com review). `fetch.result_for(game, username) -> (opponent, "win"|"loss"|"draw")`. `data/gm_blitz.csv` has the same columns as `data/gm_games.csv` (+ `accuracy`), `pool == "blitz"`. `data/gm_blitz_results.csv` columns `game,username,opponent,result`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_features.py`:

```python
def test_features_table_records_accuracy():
    g = {"url": "u1", "end_time": 1, "time_control": "600", "pgn": CASTLE,
         "white": {"username": "Me", "rating": 1700}, "black": {"username": "Opp", "rating": 1720},
         "accuracies": {"white": 81.5, "black": 74.2}}
    no_review = {k: v for k, v in g.items() if k != "accuracies"}
    t = features.features_table([g, dict(no_review, url="u2"), dict(g, url="u3", accuracies=None)], "me")
    assert list(t.accuracy[:2]) == [81.5, 74.2]
    assert t.accuracy[2:].isna().all()
```

Append to `tests/test_fetch.py`:

```python
def test_result_for_either_side():
    g = {"white": {"username": "Alice", "result": "win"}, "black": {"username": "bob", "result": "resigned"}}
    assert fetch.result_for(g, "alice") == ("bob", "win")
    assert fetch.result_for(g, "BOB") == ("Alice", "loss")
    draw = {"white": {"username": "Alice", "result": "agreed"}, "black": {"username": "bob", "result": "agreed"}}
    assert fetch.result_for(draw, "bob") == ("Alice", "draw")
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_features.py tests/test_fetch.py -k "accuracy or result_for" -v`
Expected: FAIL — `AttributeError: 'DataFrame' object has no attribute 'accuracy'`; `module 'chessstyle.fetch' has no attribute 'result_for'`.

- [ ] **Step 3: Implement**

In `chessstyle/features.py` `features_table`, add to the `rows.append({...})` dict, right after `"time_control": g["time_control"],`:

```python
                         "accuracy": (g.get("accuracies") or {}).get(side, NAN),
```

In `chessstyle/fetch.py`, append:

```python
def result_for(game, username):
    """(opponent username, 'win' | 'loss' | 'draw') from `username`'s side of a chess.com game dict."""
    me, opp = ("white", "black") if game["white"]["username"].lower() == username.lower() else ("black", "white")
    outcome = "win" if game[me]["result"] == "win" else "loss" if game[opp]["result"] == "win" else "draw"
    return game[opp]["username"], outcome
```

In `scripts/build_gm_info.py`, delete the `gm_result` function body and replace it with the alias (keeps `tests/test_build_gm_info.py` working):

```python
gm_result = fetch.result_for
```

Create `scripts/build_gm_blitz.py`:

```python
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
```

Append to `.gitignore` (after `!data/gm_results.csv`):

```
!data/gm_blitz.csv
!data/gm_blitz_results.csv
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_features.py tests/test_fetch.py tests/test_build_gm_info.py -v`
Expected: all pass.

- [ ] **Step 5: Run the script** (may take 10–30 min; run it in the background and wait for it, with `STOCKFISH_PATH` set)

Run: `STOCKFISH_PATH=... .venv/Scripts/python -u scripts/build_gm_blitz.py`
Expected: ends with `N GMs, M blitz games` (expect N ≈ 40–48, M ≈ 20k–24k). Then sanity-check:
`.venv/Scripts/python -c "import pandas as pd; b=pd.read_csv('data/gm_blitz.csv'); r=pd.read_csv('data/gm_blitz_results.csv'); print(b.username.nunique(), len(b), b.groupby('username').size().min(), b.sacrifices.isna().mean(), b.pool.unique(), len(r), r.result.value_counts().to_dict()); import os; print(os.path.getsize('data/gm_blitz.csv')//1024, 'KB')"`
Expected: min games per GM ≥ 200, sacrifice NaN share `0.0`, pool `['blitz']`, results rows = blitz rows, file well under 50 MB.

- [ ] **Step 6: Full suite, then commit**

```bash
git add chessstyle/features.py chessstyle/fetch.py scripts/build_gm_info.py scripts/build_gm_blitz.py tests/test_features.py tests/test_fetch.py .gitignore data/gm_blitz.csv data/gm_blitz_results.csv
git commit -m "feat: accuracy column and a blitz GM pool from cached archives

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Validate the blitz pool (notebook 02 + README)

**Files:**
- Modify: `notebooks/02_validation.py`, `notebooks/02_validation.ipynb` (rebuilt + executed), `README.md`

**Interfaces:**
- Consumes: `data/gm_blitz.csv` (Task 1), `match.identify(gm_games, chunk, shuffle=...) -> {"top1", "top5", "chance_top5", "tests"}`.
- Produces: a recorded PASS/FAIL against the 30% bar (the controller uses it to decide whether Tasks 3–4 ship the Blitz option).

- [ ] **Step 1: Append the blitz cell** to `notebooks/02_validation.py`

```python
# %% 5. Blitz pool: same identification test (the app matches blitz games only against GM blitz games)
blitz = pd.read_csv(fetch.DATA / "gm_blitz.csv")
print(blitz.username.nunique(), "GMs,", len(blitz), "blitz games")
b = match.identify(blitz, 100)
print(pd.DataFrame({"blitz": b, "blitz, shuffled labels": match.identify(blitz, 100, shuffle=True)}).T)
print("PASS" if b["top5"] >= 0.30 else "FAIL", f"blitz top-5 @ 100 games = {b['top5']:.0%} (bar 30%)")
```

- [ ] **Step 2: Rebuild and execute the notebook**

```bash
.venv/Scripts/python scripts/py2nb.py notebooks/02_validation.py
```
Execute with nbclient from inside `notebooks/` (nbconvert has failed silently in this repo before):
```bash
cd notebooks && ../.venv/Scripts/python -c "import nbformat, nbclient; nb=nbformat.read('02_validation.ipynb',4); nbclient.NotebookClient(nb, timeout=3600, resources={'metadata':{'path':'.'}}).execute(); nbformat.write(nb,'02_validation.ipynb')"
```
Expected: runs clean. Read the new cell's output: the blitz top-5, the shuffled-label top-5 (must be near `chance_top5`; if not, STOP and report — that is a bug, not a result) and the PASS/FAIL line.

- [ ] **Step 3: Update `README.md`**

In `## Data`, add a bullet: `- GM blitz pool (for the app's Blitz option): <n> of the same accounts, their 500 most recent blitz games (N = <games>).` In `## Results`, under the Validation bullet, add: `Blitz pool: top-5 @ 100 games = <x>% vs chance <y>% → <PASS/FAIL>.` Fill every value from the notebook output (no `<` placeholders may remain except the two in "Run it").

- [ ] **Step 4: Commit**

```bash
git add notebooks/02_validation.py notebooks/02_validation.ipynb README.md
git commit -m "docs: validate the blitz GM pool

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
Report the blitz top-5, chance, shuffled top-5 and PASS/FAIL in your final message.

---

### Task 3: 5-level style wording, quality rows, time-control plumbing

**Files:**
- Modify: `present.py`, `app.py` (backend only: `POOLS`, `gm_profiles`, `report`, `analyse`), `style.css`
- Test: `tests/test_present.py`, `tests/test_app.py`

**Interfaces:**
- Consumes: Task 1 `accuracy` column and blitz CSVs; the controller's ruling from Task 2 (PASS → include the `"blitz"` pool; FAIL → `POOLS` has only `"rapid"`).
- Produces: `present.LEVELS` (5 str), `present.SHORT` (5 str), `present.style_level(top) -> int|None`, `present.QUALITY` (5 str), `present.quality_level(score) -> int|None`, `present.quality_rows(mine, peers) -> list[dict]` (keys `measure, label, you, peers, n, level`), `present.quality_card_html(q) -> str`. `app.POOLS` (dict time_class → (games csv, results csv)), `app.gm_profiles(time_class="rapid")`, `app.report(table, gm, P, info, time_class="rapid")` adds key `"quality"`, `app.analyse(username, time_class="rapid")`.

- [ ] **Step 1: Write/update the failing tests**

In `tests/test_present.py`:
- Add:

```python
@pytest.mark.parametrize("top,level", [(0.1, 0), (0.15, 1), (0.29, 1), (0.3, 2), (0.449, 2), (0.45, 3),
                                       (0.79, 3), (0.8, 4), (2.0, 4), (float("nan"), None), (None, None)])
def test_style_level(top, level):
    assert present.style_level(top) == level


@pytest.mark.parametrize("score,level", [(-1, 0), (-0.31, 0), (-0.3, 1), (-0.11, 1), (-0.1, 2), (0.09, 2),
                                         (0.1, 3), (0.29, 3), (0.3, 4), (float("nan"), None)])
def test_quality_level(score, level):
    assert present.quality_level(score) == level


def test_quality_rows():
    mine = pd.DataFrame({"accuracy": [80.0] * 25, "material_blunders": [0.0] * 25, "time_trouble": [1] * 25})
    peers = pd.DataFrame({"accuracy": [70.0, 80.0] * 15, "material_blunders": [0, 1] * 15, "time_trouble": [0, 1] * 15})
    q = {r["measure"]: r for r in present.quality_rows(mine, peers)}
    assert [r["measure"] for r in present.quality_rows(mine, peers)] == ["accuracy", "material_blunders", "time_trouble"]
    assert q["accuracy"]["level"] == 4 and q["accuracy"]["n"] == 25 and q["accuracy"]["you"] == 80.0
    assert q["material_blunders"]["level"] == 4   # fewer blunders than peers is better
    assert q["time_trouble"]["level"] == 0        # always in time trouble is worse
    few = {r["measure"]: r for r in present.quality_rows(mine.head(5), peers)}
    assert few["accuracy"]["level"] is None and few["accuracy"]["n"] == 5
    assert few["material_blunders"]["level"] == 4


def test_quality_rows_without_accuracy_column():
    mine = pd.DataFrame({"material_blunders": [0.0] * 5, "time_trouble": [0] * 5})
    peers = pd.DataFrame({"material_blunders": [0, 1] * 5, "time_trouble": [0, 1] * 5})
    rows = present.quality_rows(mine, peers)
    assert rows[0]["measure"] == "accuracy" and rows[0]["level"] is None


def test_quality_rows_zero_spread():
    mine = pd.DataFrame({"accuracy": [80.0] * 25, "material_blunders": [0.0] * 25, "time_trouble": [0] * 25})
    peers = pd.DataFrame({"accuracy": [75.0] * 30, "material_blunders": [0.0] * 30, "time_trouble": [0] * 30})
    assert all(r["level"] is None for r in present.quality_rows(mine, peers))


def test_quality_card_html():
    q = {"measure": "accuracy", "label": "Accuracy <x>", "you": 80.0, "peers": 75.0, "n": 25, "level": 4}
    html = present.quality_card_html(q)
    assert "Excellent" in html and "80.0%" in html and "75.0%" in html and "based on 25 reviewed games" in html
    assert "&lt;x&gt;" in html and html.count('class="on"') == 1
    tt = present.quality_card_html({"measure": "time_trouble", "label": "Games in time trouble", "you": 0.4,
                                    "peers": 0.25, "n": 300, "level": 1})
    assert "40% of games" in tt and "Weak" in tt and "reviewed" not in tt
    na = present.quality_card_html({"measure": "accuracy", "label": "Accuracy", "you": float("nan"),
                                    "peers": float("nan"), "n": 3, "level": None})
    assert "Not available" in na and "review more" in na and 'class="on"' not in na
```

- Update existing tests to the 5 levels: in `test_trait_cards`, the time group (time_mid 0.86) now has `level == 4` and `summary == "Very strongly distinctive"`; the all-zero group stays `level == 0`, `"About typical for your rating"`; the no-data card stays `None` / `"Not enough data"`. In `test_trait_card_html_marks_the_step` use `level: 4` and still assert exactly one `class="on"`. `test_radar_returns_a_figure` unchanged.

In `tests/test_app.py`:
- In `test_report_has_everything_the_page_shows`, add `"quality"` to the expected key set and assert `[q["measure"] for q in r["quality"]] == ["accuracy", "material_blunders", "time_trouble"]`.
- Add:

```python
def test_report_empty_table_names_time_class():
    gm, P, info = app.gm_profiles()
    with pytest.raises(ValueError, match="no rated blitz games"):
        app.report(pd.DataFrame(), gm, P, info, time_class="blitz")


@pytest.mark.parametrize("tc", list(app.POOLS))
def test_every_pool_loads(tc):
    gm, P, info = app.gm_profiles(tc)
    assert len(P) >= 30 and {"opponent", "result"} <= set(gm.columns)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_present.py tests/test_app.py -v`
Expected: new/updated tests FAIL (`AttributeError: module 'present' has no attribute 'style_level'`, etc.).

- [ ] **Step 3: Implement `present.py`**

Replace the `LEVELS` and `SUMMARY` constants with:

```python
LEVELS = ["typical", "slightly distinctive", "clearly distinctive", "strongly distinctive", "very strongly distinctive"]
SHORT = ["typical", "slightly", "clearly", "strongly", "very strongly"]
LEVEL_CUTS = [0.15, 0.30, 0.45, 0.80]
SUMMARY = ["About typical for your rating", "Slightly distinctive", "Clearly distinctive", "Strongly distinctive",
           "Very strongly distinctive"]
QUALITY = ["Bad", "Weak", "Average", "Good", "Excellent"]
QUALITY_CUTS = [-0.3, -0.1, 0.1, 0.3]
QUALITY_MEASURES = [("accuracy", "Accuracy (chess.com game review)", True),
                    ("material_blunders", "Material blunders per game", False),
                    ("time_trouble", "Games in time trouble", False)]
MIN_REVIEWED = 20
```

Add after `_missing`:

```python
def style_level(top):
    """Strongest habit size in an area -> 0 (typical) … 4 (very strongly distinctive); None without data."""
    return None if _missing(top) else sum(top >= c for c in LEVEL_CUTS)


def quality_level(score):
    """Better-than-peers score -> 0 (Bad) … 4 (Excellent); None without data."""
    return None if _missing(score) else sum(score >= c for c in QUALITY_CUTS)


def quality_rows(mine, peers):
    """Player's current games vs opponents in the same games, for measures where better is unambiguous."""
    rows = []
    for col, label, higher_better in QUALITY_MEASURES:
        y = mine[col].dropna() if col in mine else pd.Series(dtype=float)
        p = peers[col].dropna() if col in peers else pd.Series(dtype=float)
        enough = len(y) >= (MIN_REVIEWED if col == "accuracy" else 1) and len(p) >= 2 and p.std() > 0
        score = (y.mean() - p.mean()) / p.std() * (1 if higher_better else -1) if enough else float("nan")
        rows.append({"measure": col, "label": label, "you": y.mean() if enough else float("nan"),
                     "peers": p.mean() if enough else float("nan"), "n": len(y), "level": quality_level(score)})
    return rows
```

In `trait_cards`, replace the `level = ...` line with `level = style_level(top)` (keep `top = max(..., default=None)`).

Replace `_scale_html` with a version that takes its labels:

```python
def _scale_html(level, labels=SHORT):
    cells = "".join(f'<div class="{"on" if i == level else ""}"></div>' for i in range(len(labels)))
    spans = "".join(f"<span>{s}</span>" for s in labels)
    return f'<div class="cs-scale">{cells}</div><div class="cs-scale-labels">{spans}</div>'
```

Add after `trait_card_html`:

```python
UNITS = {"accuracy": lambda x: f"{x:.1f}%", "material_blunders": lambda x: f"{x:.2f} per game",
         "time_trouble": lambda x: f"{x:.0%} of games"}


def quality_card_html(q):
    head = f'<div class="cs-card cs-quality"><h4>{esc(q["label"])}'
    if q["level"] is None:
        why = ("review more of your games on chess.com to see this" if q["measure"] == "accuracy"
               else "not enough games to compare")
        return f'{head}</h4><div class="cs-muted">Not available — {why}.</div></div>'
    fmt = UNITS[q["measure"]]
    note = f' · based on {q["n"]} reviewed games' if q["measure"] == "accuracy" else ""
    return (f'{head} <span class="cs-badge cs-q{q["level"]}">{QUALITY[q["level"]]}</span></h4>'
            f'{_scale_html(q["level"], QUALITY)}'
            f'<div class="cs-muted">You {fmt(q["you"])} · players at your rating {fmt(q["peers"])}{note}</div></div>')
```

In `radar`, change the scale to 0–4: `ax.set_ylim(0, 4)` and `ax.set_yticks([0, 1, 2, 3, 4], SHORT, color="#7a6552", fontsize=7)`; the docstring says "how distinctive each area is (centre = typical)".

- [ ] **Step 4: Implement `style.css`** — set `.cs-scale` and `.cs-scale-labels` back to `grid-template-columns: repeat(5, 1fr);` and append:

```css
.cs-badge { display: inline-block; font-family: 'Source Serif 4', serif; font-size: .8rem; font-weight: 600; padding: .05rem .5rem; border-radius: 4px; margin-left: .4rem; color: #fbf7ef; vertical-align: middle; }
.cs-q0 { background: #9b2c2c; } .cs-q1 { background: #c27c2c; } .cs-q2 { background: #7a6552; }
.cs-q3 { background: #4f7a3a; } .cs-q4 { background: #2f6b2f; }
```

- [ ] **Step 5: Implement the `app.py` backend** (page block is Task 4; only make it keep working)

Replace `gm_profiles` with (omit the `"blitz"` entry if the controller says Task 2 FAILED):

```python
POOLS = {"rapid": ("gm_games.csv", "gm_results.csv"), "blitz": ("gm_blitz.csv", "gm_blitz_results.csv")}


@st.cache_resource
def gm_profiles(time_class="rapid"):
    """GM games (with opponent and result), GM style vectors, GM profile details — for one time control."""
    games, results = POOLS[time_class]
    gm = pd.read_csv(fetch.DATA / games).merge(
        pd.read_csv(fetch.DATA / results, keep_default_na=False), on=["game", "username"], how="left")
    info = pd.read_csv(fetch.DATA / "gm_info.csv", keep_default_na=False).set_index("username")
    return gm, profile.vectors(profile.normalise(gm, gm.username.notna())), info
```

In `report`: signature `report(table, gm, P, info, time_class="rapid")`; the empty-table message becomes `f"no rated {time_class} games with 10+ moves found"`; add `"quality": present.quality_rows(mine, peers),` to the returned dict.

Replace `analyse` with:

```python
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
```

- [ ] **Step 6: Run tests, then full suite**

Run: `.venv/Scripts/python -m pytest tests/test_present.py tests/test_app.py -v`, then the full suite. Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add present.py app.py style.css tests/test_present.py tests/test_app.py
git commit -m "feat: 5-level style wording, quality rows and per-time-control GM pools

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Page — time-control switch and "How well you play"

**Files:**
- Modify: `app.py` (page block only)

**Interfaces:**
- Consumes: `app.POOLS`, `analyse(username, time_class)`, `r["quality"]`, `present.quality_card_html`, `present.section_html`.

- [ ] **Step 1: Edit the page block in `app.py`**

1. Hero text: replace `f"<p>We read your last {N_GAMES} rated rapid games on chess.com, ..."` with
   `f"<p>We read your last {N_GAMES} rated rapid or blitz games on chess.com, compare your habits with players at your rating, and find which of {n_gms} grandmasters and chess personalities play most like you.</p></div>"`.
2. In the form, after the text input and before the buttons, add (only when there is more than one pool):

```python
        options = [tc.capitalize() for tc in POOLS]
        picked = st.segmented_control("Time control", options, default="Rapid") if len(options) > 1 else "Rapid"
        time_class = (picked or "Rapid").lower()
```

3. Spinner text: `f"Reading {username}'s recent {time_class} games and comparing habits... (about 20 seconds)"`; call `r = analyse(username, time_class)`.
4. After the "Your style" block (radar + trait cards), add:

```python
    html(present.section_html("♔", "How well you play", f"compared with players at your rating, in {time_class}"))
    for col, q in zip(st.columns(3), r["quality"]):
        with col:
            html(present.quality_card_html(q))
```

5. Delete the `you, peers = r["blunders"]` block (the blunder sentence under "Your openings"); the quality panel now shows it.
6. Footer: `f'Based on {r["games"]} recent {time_class} games, rating {r["ratings"][0]}–{r["ratings"][1]}.'`.
7. "How does this work?": add a new item 1 "Pick Rapid or Blitz: your games are only compared with grandmaster games of the same speed, because time pressure changes habits." and renumber the existing items 2–5; then add a final paragraph: "**How well you play** compares your accuracy (from chess.com game review), material blunders and time trouble with your opponents in the same games: Bad, Weak, Average, Good or Excellent for your rating. Your style, above, is never rated good or bad — it only says how distinctive it is." If `len(POOLS) == 1`, omit the Rapid/Blitz item.

- [ ] **Step 2: Full suite**

Expected: all pass.

- [ ] **Step 3: AppTest check** (throwaway script outside the repo; `AppTest.from_file("D:/Projects/chess-style/app.py", default_timeout=300)`, `STOCKFISH_PATH` set)
- Click "Try an example" (`at.button[1]`) with the default Rapid: no exception/errors; markdown contains "Your style", "How well you play", "Your closest players", "% style match"; contains none of "σ", "similarity", "Stands out a lot".
- Fresh AppTest: if a segmented control exists, set it to "Blitz" (`at.button_group[0].set_value("Blitz")` or the AppTest equivalent for segmented_control), click "Try an example": same checks, and the footer says "recent blitz games". If ssgssg2 has too few blitz games, the page must show an `st.error` (not an exception) — record which happened.
- Input `nobody-xyz-123`: `at.error[0].value` contains "not found".
Paste results into the report.

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: Rapid/Blitz switch and How-well-you-play panel on the page

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
