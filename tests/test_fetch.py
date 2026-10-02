import urllib.error

import pytest

from chessstyle import fetch


def fake_api(calls):
    def get_json(url):
        calls.append(url)
        if url.endswith("/games/archives"):
            return {"archives": [f"{fetch.API}/player/me/games/2025/05"]}
        return {"games": [
            {"rules": "chess", "rated": True, "time_class": "rapid", "pgn": "1. e4 *", "url": "a"},
            {"rules": "chess960", "rated": True, "time_class": "rapid", "pgn": "1. e4 *", "url": "b"},
            {"rules": "chess", "rated": False, "time_class": "rapid", "pgn": "1. e4 *", "url": "c"},
            {"rules": "chess", "rated": True, "time_class": "blitz", "pgn": "1. e4 *", "url": "d"},
            {"rules": "chess", "rated": True, "time_class": "rapid", "url": "e"},
        ]}
    return get_json


def test_games_filters_and_caches_past_months(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fetch, "get_json", fake_api(calls))
    assert [g["url"] for g in fetch.games("Me", cache=tmp_path)] == ["a"]
    assert [g["url"] for g in fetch.games("Me", cache=tmp_path)] == ["a"]
    assert sum(c.endswith("/2025/05") for c in calls) == 1
    assert (tmp_path / "me" / "2025-05.json").exists()


def test_unknown_user_is_a_clear_error(monkeypatch):
    def get_json(url):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
    monkeypatch.setattr(fetch, "get_json", get_json)
    with pytest.raises(ValueError, match="not found"):
        fetch.games("nobody-xyz")
