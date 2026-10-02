"""Per-game style features from a chess.com PGN (python-chess; engine optional)."""
import io
import math

import chess
import chess.engine
import chess.pgn

NAN = float("nan")
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
E4_REPLIES = {"c5": "sicilian", "e5": "open", "e6": "french", "c6": "caro-kann", "d5": "scandinavian"}
D4_REPLIES = {"d5": "closed", "Nf6": "indian"}


def parse_tc(tc):
    """'600' -> (600, 0); '600+5' -> (600, 5)."""
    base, _, inc = tc.partition("+")
    return int(base), int(inc or 0)


def material(board, color):
    return sum(v * len(board.pieces(p, color)) for p, v in VALUES.items())


def non_pawn_material(board):
    return sum(material(board, c) - len(board.pieces(chess.PAWN, c)) for c in chess.COLORS)


def opening_family(sans):
    first, reply = (sans + ["", ""])[:2]
    if first == "e4":
        return E4_REPLIES.get(reply, "e4-other")
    if first == "d4":
        return D4_REPLIES.get(reply, "d4-other")
    return {"c4": "english", "Nf3": "reti"}.get(first, "other")


def _castling(color, boards, moves):
    """(own move number, 1 if queenside else 0) of `color`'s castling, or (NAN, NAN)."""
    k = 0
    for b, m in zip(boards, moves):
        if b.turn == color:
            k += 1
            if b.is_castling(m):
                return k, int(not b.is_kingside_castling(m))
    return NAN, NAN


def _time(own_clocks, base, inc):
    keys = ("time_open", "time_mid", "time_end", "time_trouble")
    if not own_clocks or None in own_clocks or not base:
        return dict.fromkeys(keys, NAN)
    total = base + inc * len(own_clocks)
    spent, prev = [], base
    for c in own_clocks:
        spent.append(prev - c + inc)
        prev = c
    phase = lambda s: sum(s) / total if s else NAN
    return {"time_open": phase(spent[:10]), "time_mid": phase(spent[10:30]), "time_end": phase(spent[30:]),
            "time_trouble": int(min(own_clocks) < 0.1 * base)}


def _swings(color, own, boards, engine, depth):
    """Placeholder until Task 3 adds the engine check: no engine -> NaN."""
    return {"sacrifices": NAN, "material_blunders": NAN}


def _side(color, own, boards, moves, clocks, base, inc, engine, depth):
    n = len(own)
    checks = captures = pawn_moves = storms = bxn = early_queen = 0
    for k, i in enumerate(own, start=1):
        b, m = boards[i], moves[i]
        piece = b.piece_type_at(m.from_square)
        checks += b.gives_check(m)
        captures += b.is_capture(m)
        early_queen |= piece == chess.QUEEN and k < 8
        bxn += piece == chess.BISHOP and b.piece_type_at(m.to_square) == chess.KNIGHT
        if piece == chess.PAWN:
            pawn_moves += 1
            rank = chess.square_rank(m.to_square) if color else 7 - chess.square_rank(m.to_square)
            near_king = abs(chess.square_file(m.to_square) - chess.square_file(b.king(not color))) <= 1
            storms += k > 10 and rank >= 3 and near_king
    return {
        "checks": checks / n, "captures": captures / n, "early_queen": int(early_queen),
        "pawn_storm": storms / n, "bishop_takes_knight": bxn, "pawn_share": pawn_moves / n,
        "bishop_pair_kept": int(len(boards[40].pieces(chess.BISHOP, color)) >= 2) if len(boards) > 40 else NAN,
        **_time([clocks[i] for i in own], base, inc),
        **_swings(color, own, boards, engine, depth),
    }


def extract(pgn, engine=None, depth=10, min_plies=20):
    """PGN text -> {"white": features, "black": features}, or None if shorter than `min_plies`."""
    game = chess.pgn.read_game(io.StringIO(pgn))
    base, inc = parse_tc(game.headers.get("TimeControl", "0"))
    board = game.board()
    boards, moves, clocks = [board.copy(stack=False)], [], []  # boards[i] = position before ply i
    for node in game.mainline():
        moves.append(node.move)
        clocks.append(node.clock())
        board.push(node.move)
        boards.append(board.copy(stack=False))
    if len(moves) < min_plies:
        return None
    queenless = [i for i, b in enumerate(boards)
                 if not b.pieces(chess.QUEEN, chess.WHITE) and not b.pieces(chess.QUEEN, chess.BLACK)]
    shared = {
        "queen_trade": int(bool(queenless)),
        "queen_trade_move": boards[queenless[0] - 1].fullmove_number if queenless else NAN,
        "material_30": material(boards[60], chess.WHITE) + material(boards[60], chess.BLACK) if len(boards) > 60 else NAN,
        "endgame": int(any(non_pawn_material(b) <= 13 for b in boards)),
        "game_len": (len(moves) + 1) // 2,
        "family": opening_family([boards[i].san(m) for i, m in enumerate(moves[:2])]),
    }
    castle = {c: _castling(c, boards, moves) for c in chess.COLORS}
    out = {}
    for color in chess.COLORS:
        own = [i for i in range(len(moves)) if boards[i].turn == color]
        f = _side(color, own, boards, moves, clocks, base, inc, engine, depth)
        move_no, long_ = castle[color]
        other = castle[not color][1]
        f.update(shared, castled=int(not math.isnan(move_no)), castle_move=move_no, castle_long=long_,
                 opposite_castle=NAN if math.isnan(long_) or math.isnan(other) else int(long_ != other))
        out["white" if color else "black"] = f
    return out
