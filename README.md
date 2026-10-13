# Which grandmaster plays like me?

You type in a chess.com username. The app reads that player's recent games, works out their
habits (how they spend the clock, when they castle, whether they trade queens early, how often
they sacrifice) and tells you which grandmasters share those habits. It also shows which games
of those GMs to look at, picked from the openings you actually play.

The catch is that a 1800 player and a grandmaster are very different in strength, so a naive
comparison just says "the GM is better". To get around that, every habit is measured against
players of the *same rating* and adjusted for the *opening* played. What's left is style, not
skill.

**Live app:** https://chess-style-kb7oec7x4aaycan7ovxt6c.streamlit.app/ (try `ssgssg2`)

## In short

- 21 style features per game, built from the moves and clock times with python-chess.
  Stockfish is only used to tell a real sacrifice from a blunder.
- Compared against ~19,000 rapid games and ~24,000 blitz games from 48 players (43 GMs plus 5
  well-known streamers), all pulled from the chess.com public API.
- Matching is cosine similarity on z-scored features, with a bootstrap to show how sure the
  match is.
- I checked that it works before trusting it: given 100 unseen games of a GM, the method puts
  the right GM in its top 5 **44%** of the time for rapid (chance is 10%; I set the pass mark
  at 30% before running it).
- 92 tests (pytest), Streamlit front end, deployed on Streamlit Community Cloud.

## The question

Comparing an 1800 to a grandmaster on raw stats mostly measures strength: GMs blunder less, convert
more and play longer games. So the question here is narrower: once rating and opening repertoire are
taken out, which GM's habits (when they trade queens, how they castle, how they spend the clock) look
most like mine?

## Data

- Me: chess.com Published-Data API, rated rapid games of `tanit0131` (N = 2,111; 1,989 with 10+ moves).
  The profile uses the 342 most recent games (rating 1629–1870).
- Peer baseline: the opponents' side of the same games, in 5 equal-count rating bands.
- GMs: 43 GMs (25 famous, 18 from the top of the rapid/blitz leaderboards) plus 5 media players, each
  with 100+ rated rapid games: 19,036 games, played 2011–2026 (median mid-2023).
- Blitz pool (for the app's Blitz option): 48 of the same accounts, up to 500 recent blitz games each
  (N = 23,837).

## Method

1. **Features.** 21 move-based features in 5 groups (aggression, king play, simplification, piece preference, time use).
2. **Opening adjustment.** Subtract the average for each opening family, so playing sharp openings
   doesn't read as a sharp style.
3. **Z-scores.** Player vs same-band peers; GMs vs the GM pool.
4. **Matching.** Each GM's profile is the mean of their games; I'm matched by cosine similarity
   (a nearest-centroid classifier, written in NumPy so it can skip missing features).
5. **Uncertainty.** 1,000 bootstrap resamples of my games give a 95% interval and P(GM in my top 3).

## Results

- My profile is close to same-rating peers almost everywhere (group means within ±0.15σ), except
  **time use (+0.48σ)**: much more clock spent in the middlegame (+0.86σ) and more time trouble
  (+0.77σ). I also castle more often (+0.35σ) but later (−0.40σ), and push fewer pawns (−0.28σ).
- The time-use gap grew steadily as I climbed, from +0.15σ at 1000–1179 to +0.54σ at 1705–1870;
  the other groups stayed near zero the whole way.
- Closest GMs: viditchess 0.80 [0.73, 0.86], P(top 3) 81%; firouzja2003 0.79 [0.74, 0.84], 88%;
  grischuk 0.79 [0.75, 0.83], 87%. All three come mostly from the shared middlegame time use.
  The top 5 is fairly stable: the two halves of my recent games share 4 of their 5 matches.

## Does it actually work?

Test: build each GM's profile from their older half of games, then take 100-game chunks of their
newer games and see if the method finds them again.

- **Rapid:** right GM in the top 5 for 44% of chunks vs 10% by chance. Pass (bar was 30%, fixed in advance).
- **Blitz:** 80%. This isn't directly comparable: GMs' recent blitz games span ~166 days against
  ~2,283 days for rapid, so train and test are close in time. With a gap between them (the middle
  20% of each GM's games dropped) it's 72% for blitz and 39% for rapid. Clock habits carry a lot of
  the blitz signal: shuffling them drops it from 80% to 51%.
- Raw features identify GMs better (54%) than opening-adjusted ones (44%), so repertoire is real
  identity signal. The adjustment removes it on purpose.
- No single feature dominates: shuffling any one costs at most 1.4 points.

## Limitations

- The opponent baseline shares some features with me (trades and game length depend on both players).
- It assumes "unusual for your level" means the same thing at 1800 and at GM level. I can't test that.
- Blunder detection only sees immediate material loss, not positional mistakes.
- Some GM rapid games are old (back to 2011).
- "How well you play" compares you with your opponents in the same games, within wins, draws and losses
  separately. Accuracy only exists for games someone reviewed on chess.com.
- Only 70 held-out chunks in the rapid test, so each accuracy figure is roughly ±6 points.

## Project layout

```
app.py, present.py, style.css   Streamlit page and the wording/charts it shows
chessstyle/                     fetch (API + cache), features, profile (bands, z-scores), match
scripts/                        build the GM pools from the API
notebooks/                      01 my style, 02 validation (.py sources, executed .ipynb)
data/                           GM feature tables the app loads
tests/                          pytest suite
```

## Run it

    py -m venv .venv && .venv/Scripts/python -m pip install -r requirements.txt
    setx STOCKFISH_PATH <path to stockfish.exe>
    .venv/Scripts/python -m streamlit run app.py
    .venv/Scripts/python -m pytest

To rebuild my notebook for another account:

    CHESS_USERNAME=<you> .venv/Scripts/python -m jupyter nbconvert --to notebook --execute --inplace notebooks/01_my_style.ipynb
