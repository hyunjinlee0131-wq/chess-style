"""Plain-language wording and chess visuals for the app. No Streamlit here, so it is unit-testable."""
import base64
import math

import chess
import chess.svg

from chessstyle import profile

SCALE = ["much less", "a bit less", "typical", "a bit more", "much more"]
LABELS = {"Aggression": "Aggression", "King play": "King safety", "Simplification": "Simplifying",
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
    "pawn_share": ("move pawns more", "move pawns less"),
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
    "reti": ("Réti Opening", "1.Nf3"), "other": ("Other first moves", ""),
}
RESULT = {"win": "Won", "loss": "Lost", "draw": "Draw"}
THAN = " than most players at your rating"


def _missing(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


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
    return f"You {_phrase(feature, z)}{THAN}.{note}"


def trait_cards(groups, vec):
    """One card per style group: label, glyph, scale step, summary sentence, up to 3 distinctive habits."""
    cards = []
    for g, fs in profile.GROUPS.items():
        step = scale_step(groups[g])
        summary = ("Not enough data" if step is None else "About typical for your rating" if step == 2
                   else SCALE[step].capitalize() + THAN)
        strong = sorted((f for f in fs if not _missing(vec[f]) and abs(vec[f]) >= 0.15), key=lambda f: -abs(vec[f]))
        cards.append({"group": g, "label": LABELS[g], "glyph": GLYPHS[g], "step": step, "summary": summary,
                      "habits": [habit(f, vec[f]) for f in strong[:3]]})
    return cards


def _pct(x):
    return max(0, round(x * 100))


def match_words(m):
    return {"pct": f"{_pct(m['sim'])}% style match", "range": f"likely {_pct(m['lo'])}–{_pct(m['hi'])}%",
            "top3": f"in the top 3 in {round(m['p_top'] * 10)} of 10 reshuffles of your games"}


def _join(parts):
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def shared_sentence(features, vec):
    parts = [_phrase(f, vec[f]) for f in features if f in vec and not _missing(vec[f])]
    return "you both " + _join(parts) if parts else ""


def differs_sentence(feature, vec):
    if feature is None or feature not in vec or _missing(vec[feature]):
        return ""
    return f"you {_phrase(feature, vec[feature])}; they tend the other way"


def blunder_words(you, peers):
    if _missing(you) or _missing(peers):
        return "not available"
    d = (you - peers) / peers if peers else 0.0
    if abs(d) < 0.1:
        return "about as often as"
    return f"{'a bit' if abs(d) < 0.3 else 'much'} {'more' if d > 0 else 'less'} often than"


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
