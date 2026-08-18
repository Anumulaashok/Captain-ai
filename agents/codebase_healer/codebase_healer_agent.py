"""
Codebase Healer — diagnoses and fixes bugs in Jarvis's OWN source code.

NOT to be confused with agents/browser_agent/self_healer.py, which recovers stuck
browser-automation sessions. This one edits Python files in this repo.

Workflow: locate the file -> propose a fix via Gemini -> write it -> verify it compiles
-> ask for user approval (core.permission_manager, tool="self_heal_code") -> commit on a
fix branch and open a PR via integrations.github. Any failure at any step rolls the file
back to its original content, so a bad fix never lands uncommitted.
"""
import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


REPO_ROOT       = _get_base_dir()
API_CONFIG_PATH = REPO_ROOT / "config" / "api_keys.json"

# Sensitive paths self-heal must never touch, even if a hallucinated/prompt-injected
# `problem`/`target_file` points at them. Being gitignored was accidentally catching
# most of this before (git add silently no-ops, commit aborts) — that's a side effect,
# not a designed control, so it's enforced explicitly here too.
_DENYLIST_PARTS = {"config", "tokens", ".git", "venv", "__pycache__"}
_DENYLIST_NAMES = {".env", "api_keys.json", "integrations.json"}

# A legitimate bug fix rewrites a file, it doesn't gut it or 5x its size — this catches a
# truncated/hallucinated rewrite before it's ever written to disk.
_MAX_SHRINK_RATIO = 0.4   # fixed file must keep at least 40% of the original's length
_MAX_GROWTH_RATIO = 3.0   # fixed file must not exceed 3x the original's length


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _is_sensitive_path(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    if parts & _DENYLIST_PARTS:
        return True
    return path.name in _DENYLIST_NAMES


def _diff_size_ok(original: str, fixed: str) -> bool:
    if not original:
        return True
    ratio = len(fixed) / len(original)
    return _MAX_SHRINK_RATIO <= ratio <= _MAX_GROWTH_RATIO


class CodebaseHealerAgent:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
        return cls._instance

    def _init(self):
        self._speak: Optional[Callable] = None

    def set_speak(self, fn: Callable) -> None:
        self._speak = fn

    def _say(self, msg: str, speak: Optional[Callable] = None) -> None:
        fn = speak or self._speak
        if fn:
            try:
                fn(msg)
            except Exception:
                pass
        print(f"[CodebaseHealer] {msg}")

    # ── Public API ────────────────────────────────────────────────────────────

    def heal(
        self,
        problem: str,
        target_file: str = "",
        speak: Optional[Callable] = None,
    ) -> str:
        """Start a diagnose-fix-verify-approve-PR cycle in the background. Returns immediately."""
        if not problem.strip():
            return "Tell me what's broken, sir — an error message or a description of the bug."

        threading.Thread(
            target=self._heal_worker,
            args=(problem.strip(), target_file.strip(), speak),
            daemon=True,
        ).start()
        return f"On it, sir — diagnosing and fixing: {problem[:120]}. I'll update you as I go."

    # ── Worker ────────────────────────────────────────────────────────────────

    def _heal_worker(self, problem: str, target_file: str, speak: Optional[Callable]) -> None:
        try:
            self._say(f"Diagnosing: {problem}", speak)

            path = self._locate_file(problem, target_file)
            if not path:
                self._say("Couldn't identify which file to fix, sir — give me a specific file path.", speak)
                return

            if _is_sensitive_path(path):
                self._say(f"'{path.relative_to(REPO_ROOT)}' is off-limits for self-heal, sir — won't touch it.", speak)
                return

            original = path.read_text(encoding="utf-8")
            self._say(f"Reading {path.relative_to(REPO_ROOT)}...", speak)

            fixed = self._propose_fix(problem, path, original)
            if not fixed or fixed.strip() == original.strip():
                self._say("Couldn't come up with a confident fix, sir.", speak)
                return

            if not _diff_size_ok(original, fixed):
                self._say(
                    f"The proposed fix changes {path.name}'s size by too much to trust "
                    "(likely a truncated or hallucinated rewrite) — not applying it, sir.",
                    speak,
                )
                return

            path.write_text(fixed, encoding="utf-8")

            ok, verify_msg = self._verify(path)
            if not ok:
                path.write_text(original, encoding="utf-8")
                self._say(f"Fix didn't verify ({verify_msg}) — rolled back, sir.", speak)
                return

            self._say(f"Fix verified ({verify_msg}). Requesting your approval, sir.", speak)

            from core.permission_manager import get_permission_manager
            pm = get_permission_manager()
            if not pm.request("self_heal_code"):
                path.write_text(original, encoding="utf-8")
                self._say("Fix declined — rolled back, sir.", speak)
                return

            self._commit_and_pr(path, problem, speak)

        except Exception as e:
            self._say(f"Self-heal failed: {e}", speak)

    def _locate_file(self, problem: str, target_file: str) -> Optional[Path]:
        if target_file:
            p = (REPO_ROOT / target_file).resolve()
            if REPO_ROOT in p.parents and p.is_file():
                return p
            return None

        py_files = [
            str(p.relative_to(REPO_ROOT))
            for p in REPO_ROOT.rglob("*.py")
            if "venv" not in p.parts and "__pycache__" not in p.parts
        ]
        try:
            import google.generativeai as genai
            genai.configure(api_key=_get_api_key())
            model = genai.GenerativeModel(model_name="gemini-2.5-flash-lite")
            prompt = (
                f"Problem: {problem}\n\nFiles in the repo:\n" + "\n".join(py_files[:300]) +
                "\n\nReply with ONLY the single most likely file path to fix, nothing else."
            )
            candidate = model.generate_content(prompt).text.strip().strip("`")
            p = (REPO_ROOT / candidate).resolve()
            if REPO_ROOT in p.parents and p.is_file():
                return p
        except Exception as e:
            print(f"[CodebaseHealer] ⚠️ File location failed: {e}")
        return None

    def _propose_fix(self, problem: str, path: Path, original: str) -> str:
        import google.generativeai as genai
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        prompt = (
            f"You are fixing a bug in this Python file: {path.name}\n\n"
            f"Problem report: {problem}\n\n"
            f"Current file content:\n```python\n{original[:12000]}\n```\n\n"
            "Reply with ONLY the complete corrected file content, no markdown fences, "
            "no explanation. Keep everything unrelated to the bug unchanged."
        )
        text = model.generate_content(prompt).text.strip()
        text = text.strip("`")
        if text.lower().startswith("python"):
            text = text[6:].strip()
        return text

    def _verify(self, path: Path) -> tuple[bool, str]:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return False, r.stderr[-500:]
        return True, "compiles cleanly"

    def _commit_and_pr(self, path: Path, problem: str, speak: Optional[Callable]) -> None:
        from integrations.github import is_ready, git_push, create_pull_request

        rel    = path.relative_to(REPO_ROOT)
        branch = f"fix/self-heal-{int(time.time())}"

        subprocess.run(["git", "checkout", "-b", branch], cwd=REPO_ROOT, capture_output=True, text=True)
        subprocess.run(["git", "add", str(rel)], cwd=REPO_ROOT, capture_output=True, text=True)
        commit = subprocess.run(
            ["git", "commit", "-m", f"fix: self-heal {rel} — {problem[:72]}"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if commit.returncode != 0:
            self._say("Nothing to commit — the fix produced no diff, sir.", speak)
            return

        if not is_ready():
            self._say(
                f"Fix committed locally on '{branch}', sir. GitHub isn't configured, "
                "so I couldn't push or open a PR — merge it manually when ready.",
                speak,
            )
            return

        push_msg = git_push(REPO_ROOT, branch)
        if "failed" in push_msg.lower():
            self._say(f"Fix committed on '{branch}' but push failed: {push_msg}", speak)
            return

        pr_msg = create_pull_request(
            REPO_ROOT,
            title=f"fix: self-heal {rel}",
            body=f"Auto-generated self-heal fix.\n\nProblem: {problem}",
            head=branch,
        )
        self._say(f"Approved and pushed, sir. {pr_msg}", speak)


def get_codebase_healer() -> CodebaseHealerAgent:
    return CodebaseHealerAgent()
