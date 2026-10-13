# Streamlit app (v2) — design

## Goal
A hosted web page where anyone types a chess.com username and gets their style profile and closest GMs
in seconds. Audience now: portfolio/showcase (README readers, recruiters). Kept open for later: a public
tool for any chess.com player (per-username caching is in; rate limiting is not).

## Scope
- In: style profile, top openings + material blunders, top-5 GM matches with intervals and reasons,
  reading list. Based on the player's **300 most recent** rated rapid games.
- Out: the climb chart and anything else needing full history; stability check; per-user rate limiting;
  other time classes; Lichess.

## Hosting
Streamlit Community Cloud from the GitHub repo (private allowed). `packages.txt` installs `stockfish`
(apt). Known cost: the app sleeps after a few idle days; the first visit then waits ~30 s.

## Architecture
- `app.py` — UI only. One function `analyse(username) -> dict` (cached) does the work by calling
  `chessstyle` modules; the rest renders it.
- `chessstyle/fetch.py` — `games(..., limit=None)`: when `limit` is set, read monthly archives
  newest-first and stop once `limit` games are collected; return the newest `limit` games in
  chronological order. `limit=None` keeps today's behaviour (all months), so notebooks and the GM pool
  build are unchanged.
- `chessstyle/features.py` — `open_engine()` falls back to `shutil.which("stockfish")` when
  `STOCKFISH_PATH` is unset (Streamlit Cloud installs it on PATH).
- `requirements.txt` gains `streamlit`; new `packages.txt` with `stockfish`.

## Data flow
1. `fetch.games(username, limit=300)`
2. `features.features_table(games, username, engine)` (Stockfish depth 10; ~6 s for 300 games locally)
3. `profile.player_frame(table)` → z-scores vs same-band opponents. With 300 games `assign_bands`
   yields 3 bands (100 games each minimum).
4. GM vectors from `data/gm_games.csv` → `profile.vectors(profile.normalise(...))`, cached once per
   server (`st.cache_resource`).
5. `match.bootstrap`, `match.explain`, `match.reading_list` as in notebook 01.

## Page
- Username input + button.
- Style profile: bar chart of the 5 group means (σ vs same-rating peers) and a feature table; features
  both players shape are flagged.
- Openings: top 6 family/side shares; material blunders per game, player vs peers.
- GM matches: top 5 with similarity, 95% interval, P(top 3), shared and differing traits.
- Reading list: game links from the closest GM in the player's top openings.
- Footer: games analysed, rating range, link to the repo/README for method and validation.

## Caching
`analyse` is wrapped in `st.cache_data(ttl=3600)` keyed by lower-cased username, so repeat lookups within
an hour don't hit chess.com. The archive disk cache still works but is ephemeral on Streamlit Cloud.

## Errors (shown with `st.error`, never a traceback)
- Unknown user: `fetch.games` raises `ValueError`.
- Too few games: `assign_bands` raises `ValueError` (needs ≥ 100 rated rapid games at 1000+).
- chess.com unreachable after retries: network error → "chess.com didn't respond, try again".
- No Stockfish found: still runs; sacrifice/blunder features show as unavailable.

## Testing
- `tests/test_fetch.py`: `limit` reads newest-first, stops early (later archive URLs never requested),
  returns games in chronological order.
- `tests/test_app.py`: `analyse` on a cached/fake game set returns the expected keys and 5 GM matches.
- Manual: `streamlit run app.py` with `tanit0131` and with an unknown username.
