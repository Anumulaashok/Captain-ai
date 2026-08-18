"""
self_heal action — voice/text entry point for the Codebase Healer agent.
Fixes bugs in Jarvis's own source code (see agents/codebase_healer). Not to be
confused with browser_control's built-in recovery (agents/browser_agent/self_healer.py).
"""
from typing import Callable

from agents.codebase_healer.codebase_healer_agent import get_codebase_healer


def self_heal(
    parameters: dict,
    player=None,
    speak: Callable | None = None,
) -> str:
    problem = (parameters.get("problem") or parameters.get("description") or "").strip()
    if not problem:
        return "Tell me what's broken, sir — an error message or bug description."

    if player:
        player.write_log(f"[SelfHeal] {problem}")

    agent = get_codebase_healer()
    if speak:
        agent.set_speak(speak)

    return agent.heal(
        problem=problem,
        target_file=parameters.get("file", ""),
        speak=speak,
    )
