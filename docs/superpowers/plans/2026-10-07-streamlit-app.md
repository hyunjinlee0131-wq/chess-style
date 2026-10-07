# Streamlit App (v2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A hosted Streamlit page: type a chess.com username, get style profile, openings, top-5 GM matches and a reading list from the 300 most recent rated rapid games.

**Architecture:** `app.py` holds a pure `report(table, gm, P)` (testable, no Streamlit calls), a cached `analyse(username)` that fetches + builds the features table, and the page rendering. Two small library changes: `fetch.games(limit=)` and an `open_engine()` PATH fallback.

**Tech Stack:** Python 3.13, Streamlit, pandas, python-chess, Stockfish (apt `stockfish` on Streamlit Community Cloud).

**Spec:** `docs/superpowers/specs/2026-10-07-streamlit-app-design.md`

## Global Constraints

- Analyse the player's **300 most recent** rated rapid games (`N_GAMES = 300`).
- `fetch.games(..., limit=None)` keeps today's behaviour (all months) so notebooks and `scripts/build_gm_pool.py` are unchanged.
- Results cached per username: `st.cache_data(ttl=3600)`; GM vectors cached once per server: `st.cache_resource`.
- Errors shown with `st.error`, never a traceback.
- No climb chart, no stability check, no rate limiting.
- Run Python via `.venv/Scripts/python`; Stockfish locally at `Tools/stockfish/stockfish-windows-x86-64-universal.exe`.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

- Username typed with spaces or capitals (`" Tanit0131 "`) → same result and same cache entry as `tanit0131` (UI strips + lower-cases; Task 3 Step 3).
- Player with fewer than 300 rapid games in total → analyse all of them, no error (Task 1 test `test_limit_larger_than_history_returns_everything`).
- Player with zero rapid games (archives exist) → clear "no rated rapid games" message, not a KeyError (Task 2 test `test_report_empty_table_is_a_clear_error`).
- Current month must still be refetched when `limit` is set (newest month is read first and never served stale from cache; Task 1 implementation keeps the `ym != now` rule — covered by reusing the same loop body).
- Stockfish missing on the host → page still renders; blunders show "unavailable" instead of `nan` (Task 3 Step 3 rendering; Task 1 test `test_open_engine_none_without_stockfish`).

---

### Task 1: Library changes: `fetch.games(limit=)` and Stockfish PATH fallback

**Files:**
- Modify: `chessstyle/fetch.py` (`games`)
- Modify: `chessstyle/features.py` (imports, `open_engine`)
- Test: `tests/test_fetch.py`, `tests/test_features.py`

**Interfaces:**
- Produces: `fetch.games(username, time_class="rapid", cache=DATA / "raw", limit=None) -> list[dict]` — with `limit`, the newest `limit` games in chronological order, reading months newest-first and stopping early.
- Produces: `features.open_engine() -> SimpleEngine | None` — `$STOCKFISH_PATH`, else `stockfish` on PATH or in `/usr/games`, else `None`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_fetch.py`:

```python
def fake_months(calls, months=("2025/03", "2025/04", "2025/05")):
    def get_json(url):
        calls.append(url)
        if url.endswith("/games/archives"):
            return {"archives": [f"{fetch.API}/player/me/games/{m}" for m in months]}
        m = url[-7:]
        return {"games": [{"rules": "chess", "rated": True, "time_class": "rapid", "pgn": "1. e4 *",
                           "url": f"{m}-{i}"} for i in (1, 2)]}
    return get_json


def test_limit_reads_newest_months_first_and_stops(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fetch, "get_json", fake_months(calls))
    got = fetch.games("me", cache=tmp_path, limit=3)
    assert [g["url"] for g in got] == ["2025/04-2", "2025/05-1", "2025/05-2"]
    assert not any(c.endswith("/2025/03") for c in calls)


def test_limit_larger_than_history_returns_everything(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "get_json", fake_months([]))
    got = fetch.games("me", cache=tmp_path, limit=10)
    assert [g["url"] for g in got] == ["2025/03-1", "2025/03-2", "2025/04-1", "2025/04-2", "2025/05-1", "2025/05-2"]
```

Append to `tests/test_features.py`:

```python
def test_open_engine_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    monkeypatch.setattr(features.shutil, "which", lambda name, path=None: "/usr/games/stockfish")
    monkeypatch.setattr(features.chess.engine.SimpleEngine, "popen_uci", lambda p: ("engine", p))
    assert features.open_engine() == ("engine", "/usr/games/stockfish")


def test_open_engine_none_without_stockfish(monkeypatch):
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    monkeypatch.setattr(features.shutil, "which", lambda name, path=None: None)
    assert features.open_engine() is None
```

(If `tests/test_features.py` doesn't already `from chessstyle import features`, add that import.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_fetch.py tests/test_features.py -k "limit or open_engine" -v`
Expected: FAIL — `games() got an unexpected keyword argument 'limit'`; `module 'chessstyle.features' has no attribute 'shutil'`.

- [ ] **Step 3: Implement**

In `chessstyle/fetch.py`, replace `games` with:

```python
def games(username, time_class="rapid", cache=DATA / "raw", limit=None):
    """Rated standard-chess games of `time_class`. Past months are read from cache; the current month is refetched.
    With `limit`, months are read newest-first until `limit` games are found; returns the newest `limit`, oldest first."""
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
```

In `chessstyle/features.py`, add `import shutil` to the stdlib imports and replace `open_engine` with:

```python
def open_engine():
    """Stockfish from $STOCKFISH_PATH, else on PATH or in /usr/games (Debian's apt location), else None
    (sacrifice/blunder features then stay NaN)."""
    path = os.environ.get("STOCKFISH_PATH") or shutil.which(
        "stockfish", path=os.environ.get("PATH", "") + os.pathsep + "/usr/games")
    return chess.engine.SimpleEngine.popen_uci(path) if path else None
```

- [ ] **Step 4: Run to verify pass, then the full suite**

Run: `STOCKFISH_PATH="D:/Projects/chess-style/Tools/stockfish/stockfish-windows-x86-64-universal.exe" .venv/Scripts/python -m pytest -q`
Expected: all passed (19 existing + 4 new = 23).

- [ ] **Step 5: Commit**

```bash
git add chessstyle/fetch.py chessstyle/features.py tests/test_fetch.py tests/test_features.py
git commit -m "feat: fetch only the newest N games; find Stockfish on PATH

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: `report()` — the analysis behind the page

**Files:**
- Create: `app.py` (imports, constants, `gm_profiles`, `report`)
- Modify: `requirements.txt` (add `streamlit`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `profile.player_frame`, `profile.vectors`, `profile.normalise`, `profile.FEATURES`, `profile.GROUPS`, `match.bootstrap` (returns DataFrame indexed by GM username with columns `sim, lo, hi, p_top`, sorted by `sim` desc), `match.explain(vec, gm_vec) -> {"shared": [...], "differs": str}`, `match.reading_list(gm_games, gm, fams) -> list[str]`.
- Produces: `report(table, gm, P) -> dict` with keys `games` (int), `ratings` (min, max), `groups` (Series indexed by `profile.GROUPS` keys), `features` (Series indexed by `profile.FEATURES`), `openings` (Series of shares, top 6), `blunders` (player mean, peer mean; may be NaN), `matches` (list of 5 dicts: `user, sim, lo, hi, p_top, shared, differs`), `reading` (list of URLs). Raises `ValueError` with a readable message when there are no player games or too few for banding.
- Produces: `gm_profiles() -> (gm DataFrame, P DataFrame)`.

- [ ] **Step 1: Install Streamlit and record it**

Run: `.venv/Scripts/python -m pip install streamlit` and add the line `streamlit` to `requirements.txt` (after `matplotlib`).

- [ ] **Step 2: Write the failing tests** — `tests/test_app.py`

```python
import pandas as pd
import pytest

import app
from chessstyle import fetch, profile


def fake_table():
    """One GM's games as 'player' vs another GM's rows as 'opponent': real feature values, valid shape."""
    gm = pd.read_csv(fetch.DATA / "gm_games.csv")
    a, b = gm.username.value_counts().index[:2]
    p = gm[gm.username == a].head(300).assign(who="player")
    p = p.assign(player_rating=p.rating)
    o = gm[gm.username == b].head(len(p)).assign(
        who="opponent", game=p.game.values, end_time=p.end_time.values, player_rating=p.rating.values)
    return pd.concat([p, o], ignore_index=True).drop(columns="pool")


def test_report_has_everything_the_page_shows():
    gm, P = app.gm_profiles()
    r = app.report(fake_table(), gm, P)
    assert set(r) == {"games", "ratings", "groups", "features", "openings", "blunders", "matches", "reading"}
    assert list(r["groups"].index) == list(profile.GROUPS)
    assert len(r["matches"]) == 5
    assert [m["sim"] for m in r["matches"]] == sorted((m["sim"] for m in r["matches"]), reverse=True)
    assert {"user", "sim", "lo", "hi", "p_top", "shared", "differs"} <= set(r["matches"][0])
    assert all(u.startswith("https://") for u in r["reading"])


def test_report_empty_table_is_a_clear_error():
    gm, P = app.gm_profiles()
    with pytest.raises(ValueError, match="no rated rapid games"):
        app.report(pd.DataFrame(), gm, P)
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 4: Implement** — `app.py`

```python
"""Which grandmaster plays like me? Streamlit page. Run: streamlit run app.py"""
import urllib.error

import pandas as pd
import streamlit as st

from chessstyle import features, fetch, match, profile

N_GAMES = 300
REPO = "https://github.com/hyunjinlee0131-wq/chess-style"


@st.cache_resource
def gm_profiles():
    gm = pd.read_csv(fetch.DATA / "gm_games.csv")
    return gm, profile.vectors(profile.normalise(gm, gm.username.notna()))


def report(table, gm, P):
    """Features table -> everything the page shows. ValueError if there are too few games."""
    if table.empty or not (table.who == "player").any():
        raise ValueError("no rated rapid games with 10+ moves found")
    z, cur = profile.player_frame(table)
    me, mine = z[cur], table[cur]
    vec = me[profile.FEATURES].mean()
    peers = table[table.game.isin(mine.game) & (table.who == "opponent")]
    boot = match.bootstrap(me, P).head(5)
    fams = (mine.family + "|" + mine.side).value_counts().head(3).index
    return {
        "games": int(cur.sum()),
        "ratings": (int(me.rating.min()), int(me.rating.max())),
        "groups": pd.Series({g: vec[fs].mean() for g, fs in profile.GROUPS.items()}),
        "features": vec,
        "openings": (mine.family + " as " + mine.side).value_counts(normalize=True).head(6),
        "blunders": (mine.material_blunders.mean(), peers.material_blunders.mean()),
        "matches": [{"user": u, **r.to_dict(), **match.explain(vec, P.loc[u])} for u, r in boot.iterrows()],
        "reading": match.reading_list(gm, boot.index[0], fams),
    }
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -v`
Expected: 2 passed (Streamlit may warn "No runtime found"; that's fine).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py requirements.txt
git commit -m "feat: app report() building the page data from a features table

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The page: `analyse()`, rendering, errors, hosting files

**Files:**
- Modify: `app.py` (append `analyse` and the page)
- Create: `packages.txt`
- Modify: `README.md` (add a "Try it" section)

**Interfaces:**
- Consumes: `report`, `gm_profiles`, `N_GAMES`, `REPO` from Task 2; `fetch.games(..., limit=)`, `features.open_engine()` from Task 1; `features.features_table(games, username, engine)`.
- Produces: the runnable page (`streamlit run app.py`).

- [ ] **Step 1: Append `analyse`** to `app.py`

```python
@st.cache_data(ttl=3600, show_spinner=False)
def analyse(username):
    games = fetch.games(username, limit=N_GAMES)
    engine = features.open_engine()
    try:
        table = features.features_table(games, username, engine)
    finally:
        if engine:
            engine.quit()
    gm, P = gm_profiles()
    return report(table, gm, P)
```

- [ ] **Step 2: Append the page** to `app.py`

```python
st.set_page_config(page_title="Which GM plays like me?", page_icon="♟")
st.title("Which grandmaster plays like me?")
st.caption(f"Your style from your last {N_GAMES} rated rapid games on chess.com, measured against players at "
           f"your rating and adjusted for openings, then matched to {len(gm_profiles()[1])} GMs. "
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
except (urllib.error.URLError, TimeoutError, OSError):
    st.error("chess.com didn't respond. Try again in a minute.")
    st.stop()

st.subheader("Style profile")
st.caption("σ = standard deviations from players at your rating; 0 = typical.")
st.bar_chart(r["groups"], horizontal=True)
rows = [(g, f, round(r["features"][f], 2), "both players shape this" if f in profile.INTERACTIVE else "")
        for g, fs in profile.GROUPS.items() for f in fs]
st.dataframe(pd.DataFrame(rows, columns=["group", "feature", "σ", "note"]), hide_index=True)

st.subheader("Openings")
left, right = st.columns(2)
left.dataframe(r["openings"].rename("share").map("{:.0%}".format))
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
for url in r["reading"]:
    st.markdown(f"- {url}")

st.caption(f"Based on {r['games']} current games, rating {r['ratings'][0]}–{r['ratings'][1]}.")
```

- [ ] **Step 3: Create `packages.txt`** with the single line:

```
stockfish
```

- [ ] **Step 4: Run the full test suite**

Run: `STOCKFISH_PATH="D:/Projects/chess-style/Tools/stockfish/stockfish-windows-x86-64-universal.exe" .venv/Scripts/python -m pytest -q`
Expected: 25 passed. (Importing `app` now also runs the page code in bare mode; `st.stop()` before any input is a no-op outside a Streamlit run. If the import fails here, move the page under `if __name__ == "__main__" or st.runtime.exists():` and rerun.)

- [ ] **Step 5: Run the page manually**

Run: `STOCKFISH_PATH="D:/Projects/chess-style/Tools/stockfish/stockfish-windows-x86-64-universal.exe" .venv/Scripts/python -m streamlit run app.py`
Check in the browser:
- ` Tanit0131 ` (spaces, capital) → all four sections render; top GM matches are plausible vs notebook 01.
- Submit the same name again → instant (cache hit).
- `nobody-xyz-123` → red "chess.com user 'nobody-xyz-123' not found".
- Empty submit → nothing happens.

- [ ] **Step 6: Add "Try it" to `README.md`** — insert directly after the intro paragraph (before `## Question`):

```markdown
## Try it
Run the web app locally: `.venv/Scripts/python -m streamlit run app.py`, then enter any chess.com username.
It analyses the 300 most recent rated rapid games (no climb chart; see the notebooks for full history).
```

- [ ] **Step 7: Commit**

```bash
git add app.py packages.txt README.md
git commit -m "feat: Streamlit page with profile, openings, GM matches and reading list

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Deploy to Streamlit Community Cloud (manual, the user's account)

**Files:**
- Modify: `README.md` (app URL)

- [ ] **Step 1: Push the branch**

Run: `git push -u origin feat/streamlit-app`

- [ ] **Step 2: User deploys** at https://share.streamlit.io → "Create app" → repo `hyunjinlee0131-wq/chess-style`, branch `feat/streamlit-app` (or `main` after merging), main file `app.py`, Python 3.13. Signing in with GitHub and granting private-repo access is the user's step.

- [ ] **Step 3: Smoke-test the hosted app** with `tanit0131` and `nobody-xyz-123` (same checks as Task 3 Step 5). Confirm blunders show a number, not "unavailable" (that proves `packages.txt` installed Stockfish and the `/usr/games` fallback found it).

- [ ] **Step 4: Put the URL in the README** — replace the "Try it" first sentence with `Live app: <the deployed URL>. Or run it locally: ...`, then commit and push:

```bash
git add README.md
git commit -m "docs: link the live app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
git push
```
