"""Regression guard: actions/open_app.py launches apps from voice/text-transcribed
names. shell=True there is a real shell-injection surface (fixed this session) — this
locks in that it never comes back."""
from pathlib import Path


def test_open_app_never_uses_shell_true():
    source = (Path(__file__).resolve().parent.parent / "actions" / "open_app.py").read_text()
    code_lines = [line for line in source.splitlines() if not line.strip().startswith("#")]
    assert "shell=True" not in "\n".join(code_lines)
