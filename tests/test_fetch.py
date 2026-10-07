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


def test_get_json_retries_timeouts(monkeypatch):
    attempts = []

    class Resp:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def read(self, *a):
            return b'{"ok": 1}'

    def urlopen(req, timeout):
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("The read operation timed out")
        return Resp()
    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(fetch.time, "sleep", lambda s: None)
    assert fetch.get_json("https://example.test") == {"ok": 1}
    assert len(attempts) == 3


def fake_months(calls, months=("2025/03", "2025/04", "2025/05")):
    def get_json(url):
        calls.append(url)
        if url.endswith("/games/archives"):
            return {"archives": [f"{fetch.API}/player/me/games/{m}" for m in months]}
        m = url[-7:]
        return {"games": [{"rules": "chess", "rated": True, "time_class": "rapid", "pgn": "1. e4 *",
                           "url": f"{m}-{i}"} for i in (1, 2)]}
    return get_json


def test_limit_reads_newest_months_first_and_stops(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(fetch, "get_json", fake_months(calls))
    got = fetch.games("me", cache=tmp_path, limit=3)
    assert [g["url"] for g in got] == ["2025/04-2", "2025/05-1", "2025/05-2"]
    assert not any(c.endswith("/2025/03") for c in calls)


def test_limit_larger_than_history_returns_everything(monkeypatch, tmp_path):
    monkeypatch.setattr(fetch, "get_json", fake_months([]))
    got = fetch.games("me", cache=tmp_path, limit=10)
    assert [g["url"] for g in got] == ["2025/03-1", "2025/03-2", "2025/04-1", "2025/04-2", "2025/05-1", "2025/05-2"]
