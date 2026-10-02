import math

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
