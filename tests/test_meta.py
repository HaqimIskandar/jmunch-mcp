from pathlib import Path

from jmunch_mcp.meta import SavingsTracker, envelope, estimate_savings


def test_savings_calc_matches_jmri_spec():
    assert estimate_savings(4000, 400) == 900  # (4000-400)//4
    assert estimate_savings(100, 500) == 0  # no negative


def test_envelope_shape(tmp_path: Path):
    tracker = SavingsTracker(path=tmp_path / "_savings.json")
    env = envelope(result={"hello": "world"}, raw_bytes=4000, response_bytes=400, tracker=tracker)
    assert "result" in env
    assert "error" not in env
    meta = env["_meta"]
    assert meta["tokens_saved"] == 900
    assert meta["total_tokens_saved"] == 900
    assert meta["response_tokens"] == 100
    assert meta["naive_tokens"] == 1000
    assert meta["retrieval_engine"] == "jmunch"
    assert meta["retrieval_version"] == "1.0"
    assert "powered_by" in meta


def test_envelope_error_shape(tmp_path: Path):
    tracker = SavingsTracker(path=tmp_path / "_savings.json")
    env = envelope(
        error={"code": "NOT_FOUND", "message": "nope"},
        raw_bytes=0,
        response_bytes=0,
        tracker=tracker,
    )
    assert "error" in env
    assert env["error"]["code"] == "NOT_FOUND"
    assert env["_meta"]["tokens_saved"] == 0


def test_tracker_persists(tmp_path: Path):
    path = tmp_path / "_savings.json"
    t1 = SavingsTracker(path=path)
    t1.record(1000)
    t1.record(500)
    assert t1.total == 1500

    t2 = SavingsTracker(path=path)
    assert t2.total == 1500
