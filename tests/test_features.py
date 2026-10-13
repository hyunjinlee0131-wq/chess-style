import math

import pytest

from chessstyle import features

HDR = '[Event "t"]\n[TimeControl "600"]\n[Result "*"]\n\n'
CASTLE = HDR + (
    "1. e4 {[%clk 0:09:58]} e5 {[%clk 0:09:57]} 2. Nf3 {[%clk 0:09:50]} Nc6 {[%clk 0:09:55]} "
    "3. Bc4 {[%clk 0:09:40]} Bc5 {[%clk 0:09:50]} 4. c3 {[%clk 0:09:30]} Nf6 {[%clk 0:09:45]} "
    "5. d3 {[%clk 0:09:20]} d6 {[%clk 0:09:40]} 6. O-O {[%clk 0:09:10]} O-O {[%clk 0:09:35]} "
    "7. Re1 {[%clk 0:09:00]} a6 {[%clk 0:09:30]} 8. a4 {[%clk 0:08:50]} Ba7 {[%clk 0:09:25]} "
    "9. h3 {[%clk 0:08:40]} h6 {[%clk 0:09:20]} 10. Nbd2 {[%clk 0:08:30]} Re8 {[%clk 0:09:15]} *")
QUEENS = HDR + (
    "1. e4 d5 2. exd5 Qxd5 3. Nc3 Qe5+ 4. Qe2 Qxe2+ 5. Bxe2 Nf6 6. Nf3 Bf5 "
    "7. d3 e6 8. Bd2 Bb4 9. O-O-O Nc6 10. a3 Ba5 *")


def test_castling_clock_and_basics():
    w = features.extract(CASTLE)["white"]
    assert (w["castled"], w["castle_move"], w["castle_long"], w["opposite_castle"]) == (1, 6, 0, 0)
    assert w["time_open"] == 90 / 600 and math.isnan(w["time_mid"]) and w["time_trouble"] == 0
    assert w["checks"] == 0 and w["pawn_share"] == 0.5 and w["game_len"] == 10
    assert w["family"] == "open" and w["queen_trade"] == 0
    assert math.isnan(w["material_30"]) and math.isnan(w["sacrifices"])


def test_queen_trade_long_castle_checks_and_no_clocks():
    f = features.extract(QUEENS)
    w, b = f["white"], f["black"]
    assert w["queen_trade"] == 1 and w["queen_trade_move"] == 5
    assert (w["castle_move"], w["castle_long"]) == (9, 1)
    assert b["castled"] == 0 and math.isnan(b["castle_move"]) and math.isnan(w["opposite_castle"])
    assert w["captures"] == 0.2 and b["checks"] == 0.2
    assert w["early_queen"] == 1 and b["early_queen"] == 1
    assert w["family"] == "scandinavian"
    assert math.isnan(w["time_open"]) and math.isnan(w["time_trouble"])


def test_short_game_skipped_and_time_control_parsing():
    assert features.extract(HDR + "1. e4 e5 2. Nf3 *") is None
    assert features.parse_tc("600") == (600, 0) and features.parse_tc("600+5") == (600, 5)


HUNG = HDR + "1. e4 e5 2. Qh5 Nc6 3. Qxe5+ Nxe5 *"
LEGAL = HDR + "1. e4 e5 2. Nf3 d6 3. Bc4 Bg4 4. Nc3 g6 5. Nxe5 Bxd1 6. Bxf7+ Ke7 7. Nd5# *"


@pytest.fixture(scope="module")
def engine():
    e = features.open_engine()
    if e is None:
        pytest.skip("STOCKFISH_PATH not set")
    yield e
    e.quit()


def test_hung_queen_is_blunder_not_sacrifice(engine):
    w = features.extract(HUNG, engine, min_plies=0)["white"]
    assert (w["sacrifices"], w["material_blunders"]) == (0, 1)


def test_sound_queen_offer_is_sacrifice(engine):
    f = features.extract(LEGAL, engine, min_plies=0)
    assert (f["white"]["sacrifices"], f["white"]["material_blunders"]) == (1, 0)
    assert f["black"]["sacrifices"] == 0


def test_features_table_rows_and_skips():
    g = {"url": "u1", "end_time": 1, "time_control": "600", "pgn": CASTLE,
         "white": {"username": "Me", "rating": 1700}, "black": {"username": "Opp", "rating": 1720}}
    short = dict(g, url="u2", pgn=HDR + "1. e4 e5 *")
    no_pgn = {k: v for k, v in g.items() if k != "pgn"}
    stranger = dict(g, url="u3", white={"username": "x", "rating": 1}, black={"username": "y", "rating": 1})
    t = features.features_table([g, short, no_pgn, stranger], "me")
    assert list(t.who) == ["player", "opponent"]
    assert list(t.rating) == [1700, 1720] and list(t.player_rating) == [1700, 1700]
    assert list(t.username) == ["me", "opp"]


def test_open_engine_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    seen = []
    monkeypatch.setattr(features.shutil, "which", lambda name, path=None: seen.append(path) or "/usr/games/stockfish")
    monkeypatch.setattr(features.chess.engine.SimpleEngine, "popen_uci", lambda p: ("engine", p))
    assert features.open_engine() == ("engine", "/usr/games/stockfish")
    assert any("/usr/games" in (p or "") for p in seen)


def test_open_engine_skips_missing_stockfish_path(monkeypatch):
    monkeypatch.setenv("STOCKFISH_PATH", "/no/such/stockfish.exe")
    monkeypatch.setattr(features.shutil, "which", lambda name, path=None: None)
    assert features.open_engine() is None


def test_open_engine_none_without_stockfish(monkeypatch):
    monkeypatch.delenv("STOCKFISH_PATH", raising=False)
    monkeypatch.setattr(features.shutil, "which", lambda name, path=None: None)
    assert features.open_engine() is None


def test_features_table_records_accuracy():
    g = {"url": "u1", "end_time": 1, "time_control": "600", "pgn": CASTLE,
         "white": {"username": "Me", "rating": 1700, "result": "win"},
         "black": {"username": "Opp", "rating": 1720, "result": "resigned"},
         "accuracies": {"white": 81.5, "black": 74.2}}
    no_review = {k: v for k, v in g.items() if k != "accuracies"}
    t = features.features_table([g, dict(no_review, url="u2"), dict(g, url="u3", accuracies=None)], "me")
    assert list(t.accuracy[:2]) == [81.5, 74.2]
    assert t.accuracy[2:].isna().all()
    assert list(t.outcome[:2]) == ["win", "loss"]
    d = dict(g, url="u4", white={"username": "Me", "rating": 1700, "result": "agreed"},
             black={"username": "Opp", "rating": 1720, "result": "agreed"})
    assert list(features.features_table([d], "me").outcome) == ["draw", "draw"]
