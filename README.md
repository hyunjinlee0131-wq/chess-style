# Which grandmaster plays like me?

Style profiling and grandmaster matching for any chess.com rapid player, measured against
players of the **same rating**, adjusted for **openings**, with an honest validation.

## Question
Comparing an 1800 to a grandmaster on raw stats mostly measures strength: GMs blunder less, convert more and
play longer games. This project asks a narrower question: once rating and opening repertoire are taken out,
which GM's habits (when they trade queens, how they castle, how they spend the clock) look most like mine?

## Data
- Player: chess.com Published-Data API, rated rapid games of `tanit0131` (N = 2,111; 1,989 with 10+ moves).
  The profile uses the 342 most recent games (rating 1629–1870).
- Peer baseline: the opponents' side of the same games, in 5 equal-count rating bands.
- GMs: 43 GMs (25 famous, 18 top of the rapid/blitz leaderboards) plus 5 media players, each with 100+
  rated rapid games: 19,036 games, played 2011–2026 (median mid-2023).

## Method
21 move-based features (python-chess) in 5 groups; Stockfish only to tell sacrifices from blunders.
Opening-family adjustment → z-scores vs same-band peers (player) / GM pool (GMs) →
cosine similarity, 1,000-sample bootstrap for uncertainty.

## Results
- My profile: style is close to same-rating peers almost everywhere (group means within ±0.15σ) except
  **time use (+0.48σ)**: much more clock spent in the middlegame (+0.86σ) and more time trouble (+0.77σ).
  I also castle more often (+0.35σ) but later (−0.40σ), and push fewer pawns (pawn share −0.28σ).
- My climb: the time-use gap grew steadily with rating, from +0.15σ at 1000–1179 to +0.54σ at 1705–1870;
  the other groups stayed near zero throughout.
- Closest GMs: viditchess 0.80 [0.73, 0.86], P(top 3) 81%; firouzja2003 0.79 [0.74, 0.84], 88%;
  grischuk 0.79 [0.75, 0.83], 87%. All three are driven by the shared middlegame time use and time trouble.
  The top 5 is fairly stable: the two halves of my recent games share 4 of their 5 matches.
- Validation: top-5 identification @ 100 games = 44% vs chance 10% → **PASS** (bar 30%, fixed in advance).
  Opening ablation: raw features identify GMs better (54%) than opening-adjusted ones (44%), so repertoire
  carries real identity signal, which the adjustment deliberately removes. Most informative features: none
  stands out; shuffling any single feature costs at most 1.4 points (captures, pawn share), so the signal is
  spread across features.

## Limitations
- Opponent baseline shares interactive features (trades, game length) with the player.
- Untestable assumption: "unusual for your level" means the same at 1800 and GM level.
- Material-blunder detection only sees immediate material loss; positional mistakes are invisible.
- GM rapid games may be years old (oldest 2011).
- The validation has only 70 held-out 100-game chunks, so each accuracy figure is ±~6 points.

## Run it
    py -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
    setx STOCKFISH_PATH <path to stockfish.exe>
    CHESS_USERNAME=<you> .venv/Scripts/python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_my_style.ipynb
    .venv/Scripts/python -m pytest
