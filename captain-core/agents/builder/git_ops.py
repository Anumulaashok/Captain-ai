"""Git operations for agent builder PR workflow."""
import logging
import os
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).parent.parent.parent.parent


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    result = subprocess.run(
        cmd,
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def create_feature_branch(agent_id: str) -> str:
    branch = f"feat/agent-{agent_id}"
    code, out, err = _run(["git", "checkout", "-b", branch])
    if code != 0 and "already exists" in err:
        _run(["git", "checkout", branch])
    return branch


def commit_agent_files(agent_id: str, message: str | None = None) -> bool:
    agent_path = f"captain-core/agents/{agent_id}/"
    _run(["git", "add", agent_path])
    _run(["git", "add", "captain-core/agents/registry.py"])
    _run(["git", "add", "captain-core/db/seed.py"])
    msg = message or f"feat: add {agent_id} agent"
    code, _, err = _run(["git", "commit", "-m", msg])
    if code != 0:
        log.warning(f"Commit failed: {err}")
        return False
    return True


def push_branch(branch: str) -> bool:
    code, _, err = _run(["git", "push", "-u", "origin", branch])
    if code != 0:
        log.warning(f"Push failed: {err}")
        return False
    return True


def create_pull_request(branch: str, title: str, body: str) -> dict:
    code, out, err = _run([
        "gh", "pr", "create",
        "--head", branch,
        "--title", title,
        "--body", body,
    ])
    if code != 0:
        return {"success": False, "error": err or "gh CLI not available"}
    # Extract PR URL from output
    pr_url = out.strip().split("\n")[-1] if out else ""
    return {"success": True, "url": pr_url, "branch": branch}


def merge_pull_request(pr_number: int) -> dict:
    code, out, err = _run(["gh", "pr", "merge", str(pr_number), "--squash"])
    return {"success": code == 0, "output": out, "error": err}
