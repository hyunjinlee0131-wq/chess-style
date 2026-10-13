"""Plain-language wording and chess visuals for the app. No Streamlit here, so it is unit-testable."""
import base64
import math
from html import escape as esc

import chess
import chess.svg
import matplotlib

matplotlib.use("Agg")
from matplotlib.figure import Figure
import numpy as np
import pandas as pd

from chessstyle import profile

SCALE = ["much less", "a bit less", "typical", "a bit more", "much more"]
LABELS = {"Aggression": "Aggression", "King play": "King play", "Simplification": "Simplifying",
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
    "pawn_share": ("make more pawn moves", "make fewer pawn moves"),
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
    "reti": ("Réti Opening", "1.Nf3"), "other": ("Other openings", ""),
}
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
RESULT = {"win": "Won", "loss": "Lost", "draw": "Draw"}
THAN = " than most players at your rating"


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def style_level(top):
    """Strongest habit size in an area -> 0 (typical) … 4 (very strongly distinctive); None without data."""
    return None if _missing(top) else sum(top >= c for c in LEVEL_CUTS)


def quality_level(score):
    """Better-than-peers score -> 0 (Bad) … 4 (Excellent); None without data."""
    return None if _missing(score) else sum(score >= c for c in QUALITY_CUTS)


def _scores(mine, peers, col, sign):
    """(score, you, peers): pooled, or the plain mean over outcomes (wins vs wins, ...) when both have `outcome`."""
    nan = float("nan")
    if "outcome" not in mine or "outcome" not in peers:
        y, p = mine[col].dropna(), peers[col].dropna()
        ok = len(y) >= (MIN_REVIEWED if col == "accuracy" else 1) and len(p) >= 2 and p.std() > 0
        return (sign * (y.mean() - p.mean()) / p.std(), y.mean(), p.mean()) if ok else (nan,) * 3
    got = []
    for o in ("win", "draw", "loss"):
        y, p = mine.loc[mine.outcome == o, col].dropna(), peers.loc[peers.outcome == o, col].dropna()
        if len(y) >= 5 and len(p) >= 5 and p.std() > 0:
            got.append((sign * (y.mean() - p.mean()) / p.std(), y.mean(), p.mean()))
    return tuple(np.mean(got, axis=0)) if got and mine[col].count() >= (MIN_REVIEWED if col == "accuracy" else 1) else (nan,) * 3


def quality_rows(mine, peers):
    """Player's current games vs opponents in the same games, for measures where better is unambiguous."""
    rows = []
    for col, label, higher_better in QUALITY_MEASURES:
        have = col in mine and col in peers
        score, you, peer = _scores(mine, peers, col, 1 if higher_better else -1) if have else (float("nan"),) * 3
        rows.append({"measure": col, "label": label, "you": you, "peers": peer,
                     "n": int(mine[col].count()) if col in mine else 0, "level": quality_level(score)})
    return rows


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
    return f"You {_phrase(feature, z)}{THAN}{note}."


def trait_cards(groups, vec):
    """One card per style group: label, glyph, how distinctive it is (0-4, None = no data), summary, up to 3 habits."""
    cards = []
    for g, fs in profile.GROUPS.items():
        have = [f for f in fs if not _missing(vec[f])]
        top = max((abs(vec[f]) for f in have), default=None)
        level = style_level(top)
        strong = sorted((f for f in have if abs(vec[f]) >= 0.15), key=lambda f: -abs(vec[f]))
        cards.append({"group": g, "label": LABELS[g], "glyph": GLYPHS[g], "level": level,
                      "summary": "Not enough data" if level is None else SUMMARY[level],
                      "habits": [habit(f, vec[f]) for f in strong[:3]]})
    return cards


def _pct(x):
    return max(0, round(x * 100))


def match_words(m):
    k = round(m["p_top"] * 10)
    return {"pct": f"{_pct(m['sim'])}% style match", "range": f"(likely between {_pct(m['lo'])}% and {_pct(m['hi'])}%)",
            "top3": f"stays in your top 3 in {k} of 10 re-checks" if k else "rarely in your top 3"}


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def shared_sentence(features, vec):
    parts = [_phrase(f, vec[f]) for f in features if f in vec and not _missing(vec[f])]
    return "you both " + _join(parts) if parts else ""


def _both(vec, gm):
    return [f for f in vec.index if f in gm and not _missing(vec[f]) and not _missing(gm[f])
            and abs(vec[f]) >= 0.15 and abs(gm[f]) >= 0.15]


def shared_features(vec, gm, k=3):
    """Features where you and the player both stand out in the same direction, strongest agreement first."""
    same = [f for f in _both(vec, gm) if vec[f] * gm[f] > 0]
    return sorted(same, key=lambda f: -vec[f] * gm[f])[:k]


def differs_feature(vec, gm):
    """The feature where you stand out in opposite directions most, or None."""
    opp = [f for f in _both(vec, gm) if vec[f] * gm[f] < 0]
    return min(opp, key=lambda f: vec[f] * gm[f], default=None)


def differs_sentence(feature, vec, name="they"):
    if feature is None or feature not in vec or _missing(vec[feature]):
        return ""
    return f"you {_phrase(feature, vec[feature])}; {name} does the opposite"


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


def section_html(glyph, title, sub=""):
    return (f'<div class="cs-section"><span class="glyph">{glyph}</span><h2>{esc(title)}</h2>'
            f'<span class="sub">{esc(sub)}</span></div>')


def _scale_html(level, labels=SHORT):
    cells = "".join(f'<div class="{"on" if i == level else ""}"></div>' for i in range(len(labels)))
    spans = "".join(f"<span>{s}</span>" for s in labels)
    return f'<div class="cs-scale">{cells}</div><div class="cs-scale-labels">{spans}</div>'


def trait_card_html(c):
    habits = "".join(f"<li>{esc(h)}</li>" for h in c["habits"])
    return (f'<div class="cs-card"><h4>{c["glyph"]} {esc(c["label"])}</h4>{_scale_html(c["level"])}'
            f'<div class="summary">{esc(c["summary"])}</div>' + (f"<ul>{habits}</ul>" if habits else "") + "</div>")


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


def photo_html(m):
    if str(m.get("avatar", "")).startswith("https://"):
        return f'<img src="{esc(m["avatar"])}" alt="{esc(m["name"])}">'
    return '<div class="placeholder">♚</div>'


def _title(m):
    return f'<span class="cs-title-badge">{esc(m["title"])}</span>' if m.get("title") else ""


def gm_hero_html(m, vec):
    w = match_words(m)
    ops = ", ".join(f'{opening_name(o["family"])} as {o["side"]} ({o["share"]:.0%})' for o in m["openings"])
    shared = shared_sentence(shared_features(vec, m["gm_features"]), vec)
    differs = differs_sentence(differs_feature(vec, m["gm_features"]), vec, m["name"])
    return (f'<div class="cs-card cs-gm">{photo_html(m)}<div>'
            f'<p class="name">{_title(m)}{esc(m["name"])} {flag(m["country"])}</p>'
            f'<div><span class="cs-pct">{w["pct"]}</span> <span class="cs-muted">{w["range"]} · {w["top3"]}</span></div>'
            + (f'<p><b>Plays like you because</b> {esc(shared)}.</p>' if shared else "")
            + (f'<p><b>Where you differ:</b> {esc(differs)}.</p>' if differs else "")
            + (f'<p><b>Favourite openings:</b> {esc(ops)}</p>' if ops else "")
            + f'<p><a href="https://www.chess.com/member/{esc(m["user"])}" target="_blank">'
              f'View {esc(m["name"])} on chess.com →</a></p></div></div>')


def gm_small_html(m, vec, rank, feature):
    w = match_words(m)
    because = shared_sentence([feature] if feature else [], vec)
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
    return ('<div class="cs-table-wrap"><table class="cs-table"><tr><th>Date</th><th>Opening</th><th>Opponent</th><th>Result</th><th></th></tr>'
            f"{body}</table></div>")


PERCENT = {"early_queen", "castled", "castle_long", "opposite_castle", "queen_trade", "endgame",
           "bishop_pair_kept", "pawn_share", "time_open", "time_mid", "time_end", "time_trouble"}


def _num(x, f):
    return "—" if _missing(x) else f"{x:.0%}" if f in PERCENT else f"{x:.2f}"


def numbers_table(r):
    rows = []
    for g, fs in profile.GROUPS.items():
        for f in fs:
            s = scale_step(r["features"][f])
            rows.append({"Area": LABELS[g], "Habit": FEATURE_NAMES[f], "You": _num(r["raw"][f], f),
                         "Players at your rating": _num(r["peer_raw"][f], f),
                         "Compared with them": "not available" if s is None else SCALE[s]})
    return pd.DataFrame(rows)


def radar(cards):
    """Five style groups: how distinctive each area is (centre = typical)."""
    labels = [c["label"] for c in cards]
    vals = [0 if c["level"] is None else c["level"] for c in cards]
    ang = np.linspace(0, 2 * np.pi, len(cards), endpoint=False).tolist()
    loop = lambda xs: xs + xs[:1]
    fig = Figure(figsize=(4.2, 4.2))  # not pyplot: nothing stays registered between lookups
    ax = fig.add_subplot(polar=True)
    fig.patch.set_facecolor("#f6efe2")
    ax.set_facecolor("#fbf7ef")
    ax.plot(loop(ang), loop(vals), color="#5b3a21", lw=2.2)
    ax.fill(loop(ang), loop(vals), color="#8b5a2b", alpha=0.25)
    ax.set_ylim(0, 4)
    ax.set_yticks([0, 1, 2, 3, 4], SHORT, color="#7a6552", fontsize=7)
    ax.set_xticks(ang, labels, fontfamily="serif", color="#2b1d12", fontsize=10)
    ax.spines["polar"].set_color("#b58863")
    ax.grid(color="#e3d5bd")
    return fig
