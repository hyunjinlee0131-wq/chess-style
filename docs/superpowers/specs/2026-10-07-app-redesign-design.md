# App redesign: chess aesthetic + plain language — design

## Goal
Make the Streamlit app (v2) look like a chess product and read clearly to someone with no statistics
background, before deploying it to Streamlit Community Cloud. Same analysis; new presentation plus
GM profile details.

## Decisions (from the user)
- Visual direction **A — classic tournament hall**: ivory and walnut-brown board colours, serif headings,
  subtle board-square motif, piece glyphs (♔ ♕ ♖ ♗ ♘) as section markers.
- **No statistical notation** anywhere on the page (no σ, z-score, standard deviation, bootstrap).
- Style profile: **both** a radar chart of the 5 groups **and** 5 trait cards.
- GM matches: **1 large card** for the #1 match + **3 smaller cards** (#2–#4).
- Reading list: rows with **date, opening, who won**, each linking to the game.
- Repo stays **private** → remove the repo link from the page.
- Defaults accepted: plain numbers as described below; board diagrams for the player's top 3 openings;
  collapsed "Show the numbers" section; GM details saved once to a committed file.

## Plain-language rules
- Scale word from a z-score `z` (vs players at the same rating, or vs the GM pool for GMs):
  `|z| < 0.15` → "typical"; `0.15 ≤ |z| < 0.45` → "a bit more"/"a bit less"; `|z| ≥ 0.45` →
  "much more"/"much less". Shown as a 5-step scale: much less · a bit less · typical · a bit more · much more.
- Every one of the 21 features has a plain phrase pair, e.g. `time_mid`: "spend more of your clock in the
  middlegame" / "spend less of your clock in the middlegame". Sentence = "You " + phrase + " than most
  players at your rating."
- Group names shown to users: Aggression, King safety, Simplifying, Piece choices, Clock use
  (mapped from `profile.GROUPS` keys).
- Match: `similarity × 100`, clamped at 0, as "80% style match"; interval as "likely 73–86%";
  P(top 3) as "in the top 3 in 8 of 10 reshuffles of your games" (rounded to tenths).
- Features both players shape (`profile.INTERACTIVE`) get a small note "your opponents affect this too".
- Missing engine values → "not available".

## Page layout (top to bottom)
1. **Header**: title "Which grandmaster plays like you?", one-line plain explanation, username form.
2. **Style profile**: radar chart (5 groups, walnut line on ivory, "typical" ring marked) beside 5 trait
   cards. Each card: glyph, group name, scale bar with the player's position, one summary sentence, and
   up to 3 distinctive habits (features in that group with `|z| ≥ 0.15`, strongest first) as sentences.
3. **Your openings**: top 3 openings as small board diagrams (python-chess SVG, walnut/ivory squares)
   with friendly name, moves and share of games; material blunders per game "you 0.59 · players at your
   rating 0.51" with a plain verdict ("a bit more often").
4. **Your closest grandmasters**: large card for #1 — photo, full name, title, country flag (emoji from
   country code), match % + likely range + top-3 phrase, "Plays like you because you both …" (shared traits
   as phrases), "Where you differ: …", their top 3 openings with share, link to their chess.com profile.
   Then 3 smaller cards (#2–#4): photo, name, title, match %, one "because" line.
5. **Study their games**: #1 GM's newest games in the player's top openings — rows: date, opening,
   opponent, result from the GM's side (Won/Lost/Draw), linking to chess.com.
6. **Show the numbers** (collapsed): per-feature table with plain labels and the scale word plus the raw
   value, for curious readers. Still no σ symbol.
7. Footer: "Based on N recent games, rating A–B."

## Data
- New one-off script `scripts/build_gm_info.py` (no Stockfish, no feature extraction):
  - `data/gm_info.csv`: `username, name, title, avatar, country` from `/pub/player/{u}` for each
    username in `gm_games.csv` (48 requests). Missing name → username; missing avatar → blank.
  - `data/gm_results.csv`: `game, opponent, result` (from the GM's side: win/loss/draw) for every game in
    `gm_games.csv`, read from the local archive cache `data/raw/<gm>/*.json` (no new downloads).
  - Both committed (`.gitignore` exceptions added like `gm_games.csv`).
- Opening family → friendly name + moves, e.g. `indian` → "Indian Defence", "1.d4 Nf6";
  `open` → "Open Game", "1.e4 e5"; catch-alls (`e4-other`, `d4-other`, `other`) get a name and the
  first move only, or no board for `other`.

## Code structure
- `present.py` (new, pure, no Streamlit): scale words, feature phrases, group labels, trait-card data,
  match wording, opening names/moves, board SVG, country flag. Unit-tested.
- `app.py`: `report()` gains `gm_info`/results inputs needed for cards and reading rows and returns top 4
  matches; page code renders HTML/CSS cards using `present.py`; radar via matplotlib (already installed).
- `style.css` (new): fonts (Google Fonts: Playfair Display for headings, Source Serif 4 for body),
  colours, card styles, board motif; injected once by `app.py`.
- `.streamlit/config.toml` (new): theme base light, ivory background, walnut primary, serif font.

## Error handling
Unchanged (friendly `st.error` for invalid/unknown user, too few games, chess.com down). A GM missing from
`gm_info.csv` falls back to username and a piece-glyph placeholder instead of a photo.

## Testing
- `tests/test_present.py`: scale-word thresholds (including exactly 0.15 and 0.45, negative side);
  every feature in `profile.FEATURES` has a phrase pair; every family in `gm_games.csv` has a name;
  board SVG for `french` contains `<svg`; match wording clamps negatives; flag from "IN" is 🇮🇳.
- `tests/test_app.py`: existing tests updated (4 matches; matches carry name/avatar; reading rows have
  date, opening, opponent, result).
- Manual: AppTest smoke run plus a look in the browser at `tanit0131`.

## Out of scope
New analysis, dark mode toggle, mobile-specific layout beyond Streamlit's default responsiveness,
live API calls for GM info at page time.
