"""
Session recorder — durable, queryable record of every agent run and every step attempt
(tool, parameters, result/error, success, duration). This is what self-heal and future
debugging reads to find out what's actually been failing, instead of relying on the user
to describe the bug from memory.

Primary store: PostgreSQL (jarvis_runs / jarvis_steps, via integrations.pg_store).
Falls back to an append-only JSON-lines file (memory/session_log.jsonl) when Postgres
isn't configured.

Respects the "Save Logs" UI toggle (core.session_settings) — when disabled, every
recording call becomes a no-op.
"""
import json
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR   = _get_base_dir()
LOG_PATH   = BASE_DIR / "memory" / "session_log.jsonl"
_file_lock = threading.Lock()


def _enabled() -> bool:
    try:
        from core.session_settings import is_save_logs_enabled
        return is_save_logs_enabled()
    except Exception:
        return True


def _pg_ready() -> bool:
    try:
        from integrations.pg_store import is_ready
        return is_ready()
    except Exception:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_json(event: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _file_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


# ── Runs ─────────────────────────────────────────────────────────────────────

def start_run(goal: str) -> str:
    run_id = uuid.uuid4().hex[:12]
    if not _enabled():
        return run_id

    if _pg_ready():
        try:
            from integrations.pg_store import record_run_start
            record_run_start(run_id, goal)
            return run_id
        except Exception as e:
            print(f"[SessionRecorder] ⚠️ PG run_start failed: {e}")

    _append_json({"type": "run_start", "run_id": run_id, "goal": goal, "ts": _now()})
    return run_id


def end_run(run_id: str, status: str, summary: str = "", replan_count: int = 0) -> None:
    if not _enabled():
        return

    if _pg_ready():
        try:
            from integrations.pg_store import record_run_end
            record_run_end(run_id, status, summary, replan_count)
            return
        except Exception as e:
            print(f"[SessionRecorder] ⚠️ PG run_end failed: {e}")

    _append_json({
        "type": "run_end", "run_id": run_id, "status": status,
        "summary": summary, "replan_count": replan_count, "ts": _now(),
    })


def record_step(
    run_id:      str,
    step_num:    int,
    tool:        str,
    parameters:  dict,
    success:     bool,
    result:      str = "",
    error:       str = "",
    duration_ms: int = 0,
) -> None:
    if not _enabled():
        return

    if _pg_ready():
        try:
            from integrations.pg_store import record_step as pg_record_step
            pg_record_step(run_id, step_num, tool, parameters, success, result, error, duration_ms)
            return
        except Exception as e:
            print(f"[SessionRecorder] ⚠️ PG record_step failed: {e}")

    _append_json({
        "type": "step", "run_id": run_id, "step": step_num, "tool": tool,
        "parameters": parameters, "success": success,
        "result": (result or "")[:1000], "error": (error or "")[:1000],
        "duration_ms": duration_ms, "ts": _now(),
    })


# ── Query helpers (used by self-heal / diagnostics) ─────────────────────────

def recent_failures(tool: str = "", hours: int = 24, limit: int = 20) -> list[dict]:
    """Recent failed steps, optionally filtered by tool — self-heal reads this to find
    out what's actually broken instead of relying on the user to describe it."""
    if _pg_ready():
        try:
            from integrations.pg_store import get_recent_failures
            return get_recent_failures(tool=tool or None, hours=hours, limit=limit)
        except Exception as e:
            print(f"[SessionRecorder] ⚠️ PG recent_failures failed: {e}")

    if not LOG_PATH.exists():
        return []

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()[-5000:]  # cap scan size

    failures = []
    for line in reversed(lines):
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("type") != "step" or ev.get("success"):
            continue
        if tool and ev.get("tool") != tool:
            continue
        failures.append(ev)
        if len(failures) >= limit:
            break
    return failures


def tool_failure_counts(hours: int = 1) -> dict[str, int]:
    """Failure count per tool in the lookback window — used to detect crash loops."""
    counts: dict[str, int] = {}
    for f in recent_failures(hours=hours, limit=1000):
        t = f.get("tool", "unknown")
        counts[t] = counts.get(t, 0) + 1
    return counts
