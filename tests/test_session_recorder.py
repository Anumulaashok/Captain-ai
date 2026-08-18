"""core/session_recorder.py's JSON fallback path and the "Save Logs" toggle — the
whole point of this module is to reliably capture what happened so issues can be
diagnosed later, so its no-op / write paths need to actually be tested, not just
eyeballed once in a terminal."""
import json

import core.session_recorder as sr
from core.session_settings import set_save_logs_enabled, is_save_logs_enabled


def test_default_logging_is_enabled():
    assert is_save_logs_enabled() is True


def test_json_fallback_writes_run_and_step(tmp_path, monkeypatch):
    log_path = tmp_path / "session_log.jsonl"
    monkeypatch.setattr(sr, "LOG_PATH", log_path)
    monkeypatch.setattr(sr, "_pg_ready", lambda: False)

    run_id = sr.start_run("test goal")
    sr.record_step(run_id, 1, "web_search", {"query": "x"}, True, result="ok", duration_ms=10)
    sr.end_run(run_id, "success", "done", 0)

    lines = [json.loads(l) for l in log_path.read_text().splitlines()]
    assert [e["type"] for e in lines] == ["run_start", "step", "run_end"]
    assert lines[0]["run_id"] == run_id
    assert lines[1]["tool"] == "web_search"
    assert lines[1]["success"] is True
    assert lines[2]["status"] == "success"


def test_toggle_off_suppresses_all_recording(tmp_path, monkeypatch):
    log_path = tmp_path / "session_log.jsonl"
    monkeypatch.setattr(sr, "LOG_PATH", log_path)
    monkeypatch.setattr(sr, "_pg_ready", lambda: False)
    monkeypatch.setattr(sr, "_enabled", lambda: False)

    run_id = sr.start_run("should not be recorded")
    sr.record_step(run_id, 1, "web_search", {}, True)
    sr.end_run(run_id, "success")

    assert not log_path.exists()


def test_recent_failures_reads_only_failed_steps(tmp_path, monkeypatch):
    log_path = tmp_path / "session_log.jsonl"
    monkeypatch.setattr(sr, "LOG_PATH", log_path)
    monkeypatch.setattr(sr, "_pg_ready", lambda: False)

    run_id = sr.start_run("goal")
    sr.record_step(run_id, 1, "web_search", {}, True, result="ok")
    sr.record_step(run_id, 2, "file_controller", {}, False, error="disk full")
    sr.end_run(run_id, "failed")

    failures = sr.recent_failures(hours=1)
    assert len(failures) == 1
    assert failures[0]["tool"] == "file_controller"
    assert failures[0]["error"] == "disk full"


def test_settings_roundtrip(tmp_path, monkeypatch):
    import core.session_settings as ss
    monkeypatch.setattr(ss, "SETTINGS_PATH", tmp_path / "app_settings.json")

    assert ss.is_save_logs_enabled() is True  # default when file doesn't exist yet
    ss.set_save_logs_enabled(False)
    assert ss.is_save_logs_enabled() is False
    ss.set_save_logs_enabled(True)
    assert ss.is_save_logs_enabled() is True
