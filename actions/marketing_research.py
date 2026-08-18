"""
Marketing research — finds real-world pain points in a given market/audience and turns
them into unique, sellable SaaS product ideas with pricing and go-to-market plans.

Reuses actions.web_search for research (no separate search API needed) and
integrations.pg_store / integrations.pinecone_memory for persistence.
"""
import json
import sys
from pathlib import Path


def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _save_idea(niche: str, ideas_text: str) -> None:
    """Best-effort persistence — Postgres first, Pinecone next, silently skip if neither ready."""
    try:
        from integrations.pg_store import is_ready, upsert_memory
        if is_ready():
            upsert_memory("marketing_idea", niche, ideas_text)
            return
    except Exception:
        pass
    try:
        from integrations.pinecone_memory import is_ready as pc_ready, store
        if pc_ready():
            store("marketing_idea", niche, ideas_text)
    except Exception:
        pass


def marketing_research(parameters: dict, player=None, speak=None) -> str:
    params = parameters or {}
    niche  = (params.get("niche") or params.get("query") or "").strip()

    if not niche:
        return "Tell me what market or audience to research, sir."

    if player:
        player.write_log(f"[Marketing] {niche}")
    if speak:
        speak(f"Researching pain points in {niche}, sir. One moment.")

    print(f"[Marketing] 🔍 Researching: {niche!r}")

    from actions.web_search import web_search

    pain_points = web_search({"query": f"{niche} frustrated complaints reddit"})
    competitors = web_search({"query": f"best {niche} software SaaS app 2026"})

    prompt = (
        "You are a product strategist. Based on the research below, propose 3 unique, "
        "sellable SaaS product ideas.\n\n"
        f"REAL-WORLD PAIN POINTS in \"{niche}\":\n{pain_points[:3000]}\n\n"
        f"EXISTING COMPETITORS:\n{competitors[:2000]}\n\n"
        "For each idea give: (1) the specific pain point it solves, (2) target customer, "
        "(3) what makes it different from the competitors above, (4) a pricing model "
        "(subscription tiers / usage-based / freemium), (5) a concrete first-100-customers "
        "go-to-market plan (channel + message). Be specific and numeric. No filler."
    )

    try:
        import google.generativeai as genai
        genai.configure(api_key=_get_api_key())
        model = genai.GenerativeModel(model_name="gemini-2.5-flash")
        ideas = model.generate_content(prompt).text.strip()
    except Exception as e:
        print(f"[Marketing] ⚠️ Idea synthesis failed: {e}")
        return f"Research done but idea synthesis failed, sir: {e}\n\n{pain_points}"

    _save_idea(niche, ideas)
    print("[Marketing] ✅ Ideas generated and saved.")

    if speak:
        speak(f"Got a few solid ideas for {niche}, sir.")

    return f"SaaS ideas for \"{niche}\":\n\n{ideas}"
