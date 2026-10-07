# Blitz matching + "How well you play" — design

## Decisions (user, 2026-10-08: "go as recommended but hold deploy")
1. **Like-for-like time control.** A Rapid / Blitz switch on the page: your rapid games are matched against GM
   rapid games, your blitz games against GM blitz games. The blitz GM pool is **validated first** with the same
   identification test as rapid (pre-registered bar: top-5 @ 100 games ≥ 30%).
2. **5-level scales.**
   - Style areas get 5 neutral levels (how distinctive, no good/bad): *typical · slightly · clearly · strongly ·
     very strongly distinctive*.
   - A new **"How well you play"** panel uses *Bad · Weak · Average · Good · Excellent* against players at your rating.
3. **Quality measures:** chess.com accuracy (where reviewed), material blunders per game (fewer is better), time
   trouble rate (less is better).
4. **Deploy is held** until this is done.

## Why not GM blitz for everyone
Matching never uses mistakes (material blunders are not a matching feature) and every score is relative to its
own group (you vs players at your rating; each GM vs the GM pool), so GMs' cleaner rapid games do not bias the
match. Blitz is added for data volume (598k cached GM blitz games vs 21k rapid), recency and pool size — but time
pressure changes habits, so it is compared like for like.

## Blitz GM pool
- Same 48 accounts as the rapid pool (so `gm_info.csv` covers them), each player's **500 most recent** rated blitz
  games (`fetch.games(u, "blitz", limit=500)` — archives are cached; only the current month is refetched).
- Features with Stockfish exactly as rapid; GM rows only; written to `data/gm_blitz.csv` (+ `pool = "blitz"`).
- Results (opponent, win/loss/draw) in `data/gm_blitz_results.csv`, same columns as `gm_results.csv`.
- Accounts with fewer than 200 blitz games are left out of the blitz pool.
- **Validation gate:** `match.identify(gm_blitz, 100)` top-5 ≥ 30% and shuffled labels at chance. Result goes
  into notebook 02 and the README. If blitz fails the bar, the switch ships **rapid-only** and the README reports
  the failure.

## Quality panel ("How well you play")
- Player's current games vs **their opponents in the same games** (players at your rating).
- Score = `(you − peers) / peers_sd` (sign flipped where lower is better); levels:
  `< −0.3` Bad, `−0.3…−0.1` Weak, `−0.1…0.1` Average, `0.1…0.3` Good, `≥ 0.3` Excellent.
- Accuracy needs chess.com's review; shown only when **≥ 20** of the player's current games have it, with
  "based on N reviewed games". Otherwise "not available — review more games on chess.com".
- Each row: measure name, level badge, a 5-cell scale, "You 78.4 · players at your rating 74.1" in plain units
  (accuracy %, blunders per game, % of games in time trouble).
- Requires a new `accuracy` column in `features.features_table` (per side, from the game's `accuracies`; NaN when
  absent). Not a matching feature.

## Style levels (replaces the 3-level scale)
Strongest habit `|z|` in the area: `< 0.15` typical; `< 0.30` slightly; `< 0.45` clearly; `< 0.80` strongly;
otherwise very strongly distinctive. Summary: "About typical for your rating" / "Slightly distinctive" … Radar
plots 0–4 with these labels.

## Page
- Form gains a **Rapid / Blitz** choice (default Rapid). Hero text and footer say "rapid" or "blitz" accordingly.
  Results cache per (username, time control).
- New section **"How well you play"** (glyph ♔) after "Your style".
- "How does this work?" mentions the time-control choice and the quality panel.

## Out of scope
Matching rapid against blitz, accuracy as a matching feature, new GMs beyond the 48.
