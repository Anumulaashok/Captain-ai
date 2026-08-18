"""
PostgreSQL store (Neon) — persistent tables for tasks, conversation history, and user facts.
Uses psycopg2 (sync). Schema auto-created on first use.
"""
import json
import time
import threading
from typing import Optional

from integrations.manager import get_credential

SERVICE = "postgres"
_lock   = threading.Lock()
_conn   = None


def _get_conn():
    global _conn
    with _lock:
        if _conn is None or _conn.closed:
            import psycopg2
            url = get_credential(SERVICE, "url")
            if not url:
                raise RuntimeError("PostgreSQL URL not configured.")
            _conn = psycopg2.connect(url)
            _conn.autocommit = True
            _init_schema(_conn)
        return _conn


def _init_schema(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jarvis_tasks (
            id          SERIAL PRIMARY KEY,
            text        TEXT        NOT NULL,
            done        BOOLEAN     DEFAULT FALSE,
            persona     TEXT        DEFAULT 'tommy',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS jarvis_memory (
            id          SERIAL PRIMARY KEY,
            category    TEXT        NOT NULL,
            key         TEXT        NOT NULL,
            value       TEXT        NOT NULL,
            persona     TEXT        DEFAULT 'tommy',
            created_at  TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(category, key)
        );

        CREATE TABLE IF NOT EXISTS jarvis_history (
            id          SERIAL PRIMARY KEY,
            persona     TEXT        NOT NULL,
            role        TEXT        NOT NULL,
            content     TEXT        NOT NULL,
            ts          TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS jarvis_watcher_state (
            service     TEXT        PRIMARY KEY,
            last_check  FLOAT       DEFAULT 0,
            last_ids    TEXT        DEFAULT '[]',
            updated_at  TIMESTAMPTZ DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS jarvis_runs (
            run_id        TEXT        PRIMARY KEY,
            goal          TEXT        NOT NULL,
            status        TEXT        DEFAULT 'running',
            summary       TEXT,
            replan_count  INTEGER     DEFAULT 0,
            started_at    TIMESTAMPTZ DEFAULT NOW(),
            ended_at      TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS jarvis_steps (
            id          SERIAL PRIMARY KEY,
            run_id      TEXT        NOT NULL,
            step_num    INTEGER,
            tool        TEXT        NOT NULL,
            parameters  TEXT,
            success     BOOLEAN,
            result      TEXT,
            error       TEXT,
            duration_ms INTEGER,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.close()


# ── Tasks ────────────────────────────────────────────────────────────────────

def add_task(text: str, persona: str = "tommy") -> dict:
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO jarvis_tasks (text, persona) VALUES (%s, %s) RETURNING id, text, done, created_at",
        (text, persona)
    )
    row = cur.fetchone()
    cur.close()
    return {"id": row[0], "text": row[1], "done": row[2], "created": str(row[3])}


def list_tasks(done: Optional[bool] = None, persona: str = None) -> list[dict]:
    cur   = _get_conn().cursor()
    query = "SELECT id, text, done, persona, created_at FROM jarvis_tasks"
    args  = []
    wheres = []
    if done is not None:
        wheres.append("done = %s"); args.append(done)
    if persona:
        wheres.append("persona = %s"); args.append(persona)
    if wheres:
        query += " WHERE " + " AND ".join(wheres)
    query += " ORDER BY created_at DESC LIMIT 50"
    cur.execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return [{"id": r[0], "text": r[1], "done": r[2], "persona": r[3], "created": str(r[4])} for r in rows]


def complete_task(task_id: int) -> bool:
    cur = _get_conn().cursor()
    cur.execute("UPDATE jarvis_tasks SET done=TRUE, updated_at=NOW() WHERE id=%s", (task_id,))
    updated = cur.rowcount > 0
    cur.close()
    return updated


def delete_task(task_id: int) -> bool:
    cur = _get_conn().cursor()
    cur.execute("DELETE FROM jarvis_tasks WHERE id=%s", (task_id,))
    deleted = cur.rowcount > 0
    cur.close()
    return deleted


def clear_completed() -> int:
    cur = _get_conn().cursor()
    cur.execute("DELETE FROM jarvis_tasks WHERE done=TRUE")
    n = cur.rowcount
    cur.close()
    return n


# ── Memory ───────────────────────────────────────────────────────────────────

def upsert_memory(category: str, key: str, value: str, persona: str = "tommy") -> None:
    cur = _get_conn().cursor()
    cur.execute("""
        INSERT INTO jarvis_memory (category, key, value, persona)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (category, key) DO UPDATE
            SET value=EXCLUDED.value, persona=EXCLUDED.persona, created_at=NOW()
    """, (category, key, value, persona))
    cur.close()


def get_memory(category: str = None, persona: str = None) -> list[dict]:
    cur   = _get_conn().cursor()
    query = "SELECT category, key, value, persona FROM jarvis_memory"
    args  = []
    wheres = []
    if category:
        wheres.append("category=%s"); args.append(category)
    if persona:
        wheres.append("persona=%s"); args.append(persona)
    if wheres:
        query += " WHERE " + " AND ".join(wheres)
    query += " ORDER BY created_at DESC"
    cur.execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return [{"category": r[0], "key": r[1], "value": r[2], "persona": r[3]} for r in rows]


# ── Conversation history ─────────────────────────────────────────────────────

def append_history(persona: str, role: str, content: str) -> None:
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO jarvis_history (persona, role, content) VALUES (%s, %s, %s)",
        (persona, role, content[:2000])
    )
    cur.close()


def get_history(persona: str, limit: int = 20) -> list[dict]:
    cur = _get_conn().cursor()
    cur.execute(
        "SELECT role, content, ts FROM jarvis_history WHERE persona=%s ORDER BY ts DESC LIMIT %s",
        (persona, limit)
    )
    rows = cur.fetchall()
    cur.close()
    return [{"role": r[0], "content": r[1], "ts": str(r[2])} for r in reversed(rows)]


# ── Watcher state ─────────────────────────────────────────────────────────────

def get_watcher_state(service: str) -> dict:
    cur = _get_conn().cursor()
    cur.execute("SELECT last_check, last_ids FROM jarvis_watcher_state WHERE service=%s", (service,))
    row = cur.fetchone()
    cur.close()
    if row:
        return {"last_check": row[0], "last_ids": json.loads(row[1])}
    return {"last_check": 0.0, "last_ids": []}


def set_watcher_state(service: str, last_check: float, last_ids: list) -> None:
    cur = _get_conn().cursor()
    cur.execute("""
        INSERT INTO jarvis_watcher_state (service, last_check, last_ids)
        VALUES (%s, %s, %s)
        ON CONFLICT (service) DO UPDATE
            SET last_check=EXCLUDED.last_check, last_ids=EXCLUDED.last_ids, updated_at=NOW()
    """, (service, last_check, json.dumps(last_ids)))
    cur.close()


# ── Session recording (runs / steps) ────────────────────────────────────────

def record_run_start(run_id: str, goal: str) -> None:
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO jarvis_runs (run_id, goal) VALUES (%s, %s) "
        "ON CONFLICT (run_id) DO NOTHING",
        (run_id, goal),
    )
    cur.close()


def record_run_end(run_id: str, status: str, summary: str = "", replan_count: int = 0) -> None:
    cur = _get_conn().cursor()
    cur.execute(
        "UPDATE jarvis_runs SET status=%s, summary=%s, replan_count=%s, ended_at=NOW() WHERE run_id=%s",
        (status, summary, replan_count, run_id),
    )
    cur.close()


def record_step(
    run_id: str, step_num: int, tool: str, parameters: dict,
    success: bool, result: str = "", error: str = "", duration_ms: int = 0,
) -> None:
    cur = _get_conn().cursor()
    cur.execute(
        "INSERT INTO jarvis_steps (run_id, step_num, tool, parameters, success, result, error, duration_ms) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (run_id, step_num, tool, json.dumps(parameters, default=str), success,
         (result or "")[:1000], (error or "")[:1000], duration_ms),
    )
    cur.close()


def get_recent_failures(tool: Optional[str] = None, hours: int = 24, limit: int = 20) -> list[dict]:
    cur = _get_conn().cursor()
    # `hours` is always an internally-controlled int (never raw user text), so it's safe
    # to interpolate directly — psycopg2 can't parameterize %s inside an INTERVAL literal.
    query = (
        "SELECT run_id, step_num, tool, parameters, result, error, duration_ms, created_at "
        f"FROM jarvis_steps WHERE success = FALSE AND created_at >= NOW() - INTERVAL '{int(hours)} hours'"
    )
    args: list = []
    if tool:
        query += " AND tool = %s"
        args.append(tool)
    query += " ORDER BY created_at DESC LIMIT %s"
    args.append(limit)
    cur.execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return [
        {
            "run_id": r[0], "step": r[1], "tool": r[2],
            "parameters": json.loads(r[3]) if r[3] else {},
            "result": r[4], "error": r[5], "duration_ms": r[6], "ts": str(r[7]),
        }
        for r in rows
    ]


def is_ready() -> bool:
    try:
        return bool(get_credential(SERVICE, "url"))
    except Exception:
        return False
