# Which grandmaster plays like me?

You type in a chess.com username and pick Rapid or Blitz. The app reads that player's last 300
games, works out their habits (how they spend the clock, when they castle, whether they trade
queens early, how often they sacrifice) and tells you which grandmasters share those habits.
Then it lists that grandmaster's games in the openings you actually play, so you know what to
study next.

The catch is that a 1800 player and a grandmaster are very different in strength, so a naive
comparison just says "the GM is better". To get around that, every habit is measured against
players of the *same rating* and adjusted for the *opening* played. What's left is style, not
skill.

**Live app:** https://chess-style-kb7oec7x4aaycan7ovxt6c.streamlit.app/ (try `ssgssg2`)

## In short

- 21 style features per game, built from the moves and clock times with python-chess.
  Stockfish is only used to tell a real sacrifice from a blunder.
- Two separate GM pools, one for rapid (~19,000 games) and one for blitz (~24,000 games), from
  48 players (43 GMs plus 5 well-known streamers), all pulled from the chess.com public API.
- Matching is cosine similarity on z-scored features, with a bootstrap to show how sure the
  match is.
- I checked that it works before trusting it: given 100 unseen games of a GM, the method puts
  the right GM in its top 5 **44%** of the time in rapid and **80%** in blitz (chance is 10%).
- 92 tests (pytest), Streamlit front end, deployed on Streamlit Community Cloud.

## Why I built it

I wanted to know which grandmasters play the most like me, so I could learn from them by going
through their games. Copying "the best player" isn't much help if their style has nothing to do
with mine. A GM who makes the same kind of decisions I do, in the openings I play, is a much
better teacher.

The hard part is that raw stats mostly measure strength: GMs blunder less, convert more and
play longer games. So the real question is narrower: once rating and opening repertoire are
taken out, whose habits look most like mine?

## What the app shows

1. **Your style.** Five groups of habits (aggression, king play, simplifying, piece preference,
   clock use), each on a 5-step scale from "much less" to "much more" than players at your
   rating, plus a radar chart. Style is never called good or bad, only how distinctive it is.
2. **How well you play.** Accuracy (when chess.com game review exists), material blunders and
   time trouble, rated from Bad to Excellent for your rating. Wins are compared with other
   players' wins and losses with losses, so a lucky streak doesn't make you look better.
3. **Your openings.** Your three most played, with a board for each.
4. **Your closest players.** The top match with what you share and where you differ, plus the
   next three.
5. **Games to study.** The top match's newest games in your openings, with links to chess.com.

## Data

- Your games: the last 300 rated games in the chosen time control, from the chess.com
  Published-Data API. Your opponents in those same games are the "players at your rating".
- Rapid pool: 48 accounts with 100+ rated rapid games each, 19,036 games played 2011–2026
  (median mid-2023).
- Blitz pool: the same 48 accounts, up to 500 recent blitz games each (23,837 games).
- Your rapid games are only ever compared with GM rapid games, and blitz with blitz, because
  time pressure changes habits.

## Method

1. **Features.** 21 move-based features in 5 groups (aggression, king play, simplification,
   piece preference, time use).
2. **Opening adjustment.** Subtract the average for each opening family, so playing sharp
   openings doesn't read as a sharp style.
3. **Z-scores.** You vs your opponents; GMs vs the GM pool for that time control.
4. **Matching.** Each GM's profile is the mean of their games, and you're matched by cosine
   similarity (a nearest-centroid classifier, written in NumPy so it can skip missing features).
5. **Uncertainty.** Your games are resampled 1,000 times, which gives the "likely between"
   range and the chance that a GM stays in your top 3.

## Does it actually work?

Test: build each GM's profile from their older games, then take 100-game chunks of their newer
games and see if the method finds the right GM again.

| | Rapid | Blitz |
|---|---|---|
| Right GM in top 5 | 44% | 80% |
| Same, with a gap between old and new games | 39% | 72% |
| Picking at random | 10% | 10% |

- The pass mark was 30% top 5, set before I ran the test. Both pools pass.
- Blitz looks better partly because a GM's last 500 blitz games cover a few months, while their
  rapid games go back years. Leaving a gap between the old and new games narrows it a bit.
- Clock habits carry a lot of the blitz signal: shuffling them drops blitz from 80% to 51%.
- Openings are a real part of a player's identity (raw features score 54% in rapid), but I take
  them out on purpose, because the point is to find style, not a shared repertoire.

On my own rapid games, the thing that stood out was clock use: I spend a lot more time in the
middlegame than players at my rating, and get into time trouble more. My closest matches were
Vidit, Firouzja and Grischuk, mostly because of that.

## Limitations

- My opponents are the comparison group, but some habits (like trading queens or long games)
  depend on both players, so the comparison is a bit softer there.
- It assumes being unusual at 1800 means the same as being unusual at GM level. I can't really
  test that.
- Blunders here are only pieces dropped straight away. Slower positional mistakes don't show.
- Some GM rapid games are quite old, back to 2011.
- Accuracy only shows up if you (or your opponent) ran game review on chess.com.
- The tests use around 70 chunks of games, so each percentage could be off by about 6 points.

## Project layout

```
app.py              the Streamlit page: lookup form, Rapid/Blitz switch, all the sections
present.py          turns numbers into wording, cards, the radar chart and opening boards
style.css           the chess theme (.streamlit/config.toml holds the colours)
packages.txt        tells Streamlit Cloud to install Stockfish
chessstyle/
  fetch.py          chess.com API client with caching and retries
  features.py       the 21 features per game, Stockfish for sacrifices and blunders
  profile.py        rating bands, opening adjustment, z-scores
  match.py          cosine matching, bootstrap, games to study, the validation test
scripts/            one-off builds of the rapid and blitz GM pools and GM profile info
notebooks/          01 my own style, 02 validation (.py sources and executed .ipynb)
data/               GM feature tables and game results the app loads (rapid and blitz)
tests/              pytest suite (92 tests)
```

## What I learned

- **Working with a real API.** Pulling tens of thousands of games from chess.com.
- **Turning a game into numbers.** Deciding what counts as a "habit", then computing it from
  moves and clock times with python-chess. Using Stockfish from code to tell a sacrifice from
  a blunder.
- **Similarity matching.** How a nearest-centroid classifier with cosine similarity works.
- **Validation of method.** Bootstrapping the test to make sure it's reasonable, holding out games, setting a pass mark before
  looking, comparing against chance, and shuffling features to see which ones matter.
