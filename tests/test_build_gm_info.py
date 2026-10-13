import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_gm_info", Path(__file__).resolve().parent.parent / "scripts" / "build_gm_info.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def game(white_result, black_result):
    return {"white": {"username": "Alice", "result": white_result},
            "black": {"username": "bob", "result": black_result}}


def test_gm_result_from_either_side():
    assert mod.gm_result(game("win", "resigned"), "alice") == ("bob", "win")
    assert mod.gm_result(game("win", "resigned"), "BOB") == ("Alice", "loss")
    assert mod.gm_result(game("agreed", "agreed"), "bob") == ("Alice", "draw")
    assert mod.gm_result(game("timeout", "win"), "alice") == ("bob", "loss")
