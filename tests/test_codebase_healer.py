"""Self-heal's two safety nets, added this session: a denylist so it can never target
sensitive files, and a diff-size sanity check so a truncated/hallucinated rewrite is
rejected before it's ever written to disk."""
from pathlib import Path

from agents.codebase_healer.codebase_healer_agent import (
    REPO_ROOT, _is_sensitive_path, _diff_size_ok,
)


def test_api_keys_json_is_denied():
    assert _is_sensitive_path((REPO_ROOT / "config" / "api_keys.json").resolve()) is True


def test_dotenv_is_denied():
    assert _is_sensitive_path((REPO_ROOT / ".env").resolve()) is True


def test_tokens_directory_is_denied():
    assert _is_sensitive_path((REPO_ROOT / "config" / "tokens" / "gmail.json").resolve()) is True


def test_ordinary_source_file_is_allowed():
    assert _is_sensitive_path((REPO_ROOT / "actions" / "weather_report.py").resolve()) is False


def test_identical_size_diff_is_ok():
    assert _diff_size_ok("x" * 500, "y" * 500) is True


def test_severely_truncated_fix_is_rejected():
    # A hallucinated/cut-off response gutting a 1000-char file down to 100 must not pass.
    assert _diff_size_ok("x" * 1000, "y" * 100) is False


def test_bloated_fix_is_rejected():
    assert _diff_size_ok("x" * 1000, "y" * 5000) is False


def test_reasonable_growth_is_allowed():
    # A real bug fix can legitimately add a guard clause or two — some growth is fine.
    assert _diff_size_ok("x" * 1000, "y" * 1300) is True


def test_empty_original_never_blocked_by_ratio():
    assert _diff_size_ok("", "brand new content") is True
