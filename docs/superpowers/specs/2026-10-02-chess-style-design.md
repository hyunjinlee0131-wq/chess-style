# Chess Style Matcher — Design Spec

Date: 2026-10-02 · Author: Hyunjin Lee · Status: draft for review

## 1. Goal

A portfolio data science project (target: data scientist internships/grad roles) that the author
also uses personally. Given a chess.com username, it:

1. Profiles the player's **style** relative to players of the **same strength**.
2. Shows how that style **changed as their rating climbed**.
3. Matches them to the **grandmasters with the most similar style**, with reasons and uncertainty.
4. Suggests **GM games to study** in openings the player actually plays.

The project-level deliverable is an honest **validation** of whether the style features carry
real signal, plus a README write-up (question → data → method → results → limitations).

### Scope

- **v1 (this spec):** runs locally from notebooks for any username; developed against the
  author's account (`~2,000` 10-min rapid games, rating 500 → 1800 from May 2025 to Oct 2026).
- **v2 (later, not in this spec):** hosted Streamlit app (`app.py`) calling the same modules.
- **Out of scope:** neural style embeddings (Maia / transformer stylometry), pawn-structure
  features, Lichess data. Mentioned as future work.

### Design rule: any username

Nothing is tuned to the author's account. All thresholds are relative (e.g. "current" =
current rating − 150), rating bands are computed per player, caches are keyed by lower-cased
username, and accounts with too few games get a clear message rather than a crash.

## 2. Data

All data comes from the chess.com Published-Data API (public, read-only, no key).

| Dataset | Source | Notes |
|---|---|---|
| Player games | `/pub/player/{u}/games/archives` → monthly archives | Keep rated, standard-chess, `time_class == "rapid"` games with ≥ 10 moves |
| Peer baseline | The **opponent side** of the player's own games | Same platform, time control and rating — no rating conversion needed |
| GM pool | `/pub/titled/GM` → `/pub/player/{u}/stats` → archives | Rapid games, ≥ 200 per GM, pick ~50 (most games + well-known names) |

Measured on 2026-10-02 (150-GM random sample of 1,744 GM accounts): ~116 GMs have ≥ 200
lifetime rapid games. Blitz is a **fallback only** if filtering (recency, base time) leaves
fewer than 30 GMs; any blitz-based GM is labelled as such.

**API etiquette:** serial requests, `User-Agent` with contact email, retry with backoff on 429.

**Storage:** raw PGN cached at `data/raw/{username}/{yyyy-mm}.pgn` (past months never refetched);
feature tables as CSV in `data/`. `data/` is gitignored except `data/gm_profiles.csv`, which is
committed so the later app needs no rebuild.

**Known bias:** the opponent baseline played *against the player*, so interactive features
(trades, game length) are partly shared. These features are flagged in output. Upgrade path:
sample opponents' other games.

## 3. Handling the rating climb

- **Current profile & GM match:** games where the player's rating ≥ current rating − 150
  (author: ≥ 1650, ~300–450 games). If fewer than 200 games, widen to − 250.
- **Rating bands:** player history (games rated ≥ 1000) split into ~5 **equal-count** bands (quantiles), not fixed
  widths. Each game is compared to **opponents in the same band**, which removes most strength drift.
- **Below 1000:** excluded from style features (hung pieces look like sacrifices); still shown
  as rating context in the climb chart. Bands with too few games are merged.

## 4. Features

Computed per game per side from moves only (python-chess), then aggregated per player.

| Group | Features |
|---|---|
| Aggression | checks / move · captures / move · sacrifices / game · early queen move (before move 8) |
| King play | castled rate · castling move number · kingside/queenside split · opposite-side castling rate · pawn storms toward enemy king |
| Simplification | queen-trade rate & move number · material on board at move 30 · endgame-reached rate · game length |
| Piece preference | bishop-for-knight trade rate · bishop pair kept · pawn-move share |
| Time use | time spent as share of total available (base + increment × moves) per phase · time-trouble rate |
| Openings | first move as White · reply to 1.e4 / 1.d4 · opening family (reported separately, **not** in the match) |

**Sacrifice vs blunder.** Candidate = own move after which the side is down ≥ 2 pawns of
material not regained within 2 moves. Each candidate is checked with Stockfish at low depth:
eval drop < ~1 pawn → **sacrifice**, else **blunder**. ~2 candidates/game → a few minutes for
2,000 games. Blunder rate is reported in the profile (not used in matching — it measures strength).

**Time-control comparability.** Time features use share of total available time. If GM rapid
games span very different base times, restrict to base 10–15 min when that leaves enough games.

## 5. Normalisation

1. **Opening adjustment.** Each game gets one of ~10–15 opening families (by first moves),
   separately for White and Black. Within each cohort, subtract the family mean of each feature.
   Families with too few games in a cohort merge into "other".
2. **Cohort z-scores.** Player features are z-scored against same-band opponents; GM features
   against the GM pool.
3. **Player vector** = mean of adjusted, z-scored per-game features.

**Untestable assumption (stated in README):** a deviation "relative to your level" means the
same thing at 1800 and at GM level.

## 6. Matching

- **Similarity:** cosine similarity between player vector and each GM vector (shape of style,
  not magnitude). All features weighted equally (approach 1).
- **Explanation:** per-feature contribution = product of the two z-values; show top 3 shared
  traits and the largest difference.
- **Uncertainty:** bootstrap the player's games (1,000 resamples) → ± on each similarity and
  "P(GM in top 3)". Overlapping matches are displayed as ties.
- **Repertoire match:** separate list of GMs sharing the player's opening families.
- **Reading list:** games by the top match in the player's opening families, ranked by
  opening overlap, linked to chess.com.

## 7. Validation (notebook `02_validation.ipynb`)

1. **GM identification:** per GM, profile from earliest 70% of games (time split, not random);
   test on chunks of 25 / 50 / 100 later games. Report top-1 and top-5 accuracy vs chance
   (2% / 10% at 50 GMs).
2. **Opening ablation:** same test without opening adjustment.
3. **Feature importance:** permutation — shuffle one feature, measure accuracy drop.
4. **Player stability:** split the player's recent games in halves; top matches should agree.
5. **Sanity:** shuffled GM labels → chance accuracy.

**Pass bar (fixed in advance):** top-5 accuracy at 100-game chunks ≥ 30% (3× chance).
Below it → add approach 2 (LDA / logistic-regression-weighted space) and re-test. If that also
fails, the README reports it.

**Optional later experiment:** compare each GM's rapid vs blitz profile — how much does time
pressure change style?

## 8. Output (per username)

1. Style profile (current games): per-group z-scores vs same-rating peers, opening repertoire, blunder rate.
2. Climb chart: each feature across rating bands.
3. GM matches: top 5 with similarity ± CI, reasons, ties shown.
4. Reading list: GM games in the player's openings.

## 9. Code layout

```
chess-style/
├── README.md
├── requirements.txt          # python-chess, pandas, numpy, scikit-learn, matplotlib, jupyter, pytest
├── chessstyle/
│   ├── fetch.py              # urllib API client, PGN cache, 429 retry
│   ├── features.py           # game + side → feature dict; sacrifice check
│   ├── profile.py            # opening families, bands, adjustment, z-scores, player vector
│   └── match.py              # cosine, explanations, bootstrap, reading list
├── scripts/build_gm_pool.py  # one-off GM pool → data/gm_profiles.csv
├── notebooks/01_my_style.ipynb, 02_validation.ipynb
├── tests/test_features.py, test_profile.py, test_match.py
└── data/                     # gitignored except gm_profiles.csv
```

Plain functions, no classes/config/DB/CLI. Stockfish via `chess.engine` with `STOCKFISH_PATH`
env var. GM pool and user go through the same functions.

## 10. Testing

- `test_features.py`: hand-written PGNs with known answers (castle move, queen trade, clock
  parsing, sound sacrifice vs hung queen — engine tests skip if `STOCKFISH_PATH` unset).
- `test_profile.py`: after opening adjustment, family means = 0; after z-scoring, std = 1.
- `test_match.py`: identical vectors → similarity 1; self is top match.
- `fetch.py` is not unit-tested (thin network wrapper); verified by running on a real account.

**Done for v1:** `pytest` green, `01_my_style.ipynb` runs end-to-end for the author's username,
validation results written into the README whatever they are.

## 11. Publishing

Local git repo at `D:\chess-style`. Pushed to a public GitHub repo only when the author decides.
