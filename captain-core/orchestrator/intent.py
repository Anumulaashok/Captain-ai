"""Intent classification — routes user input to the correct agent(s)."""
import json
import logging
from pydantic import BaseModel

log = logging.getLogger(__name__)

INTENT_TYPES = [
    "simple_chat",
    "coding_task",
    "email_task",
    "browser_task",
    "calendar_task",
    "file_task",
    "terminal_task",
    "research_task",
    "multi_agent",
]

CLASSIFICATION_PROMPT = """Classify the user's intent into ONE of these categories:
- simple_chat: general conversation, questions, explanations
- coding_task: write, debug, review, explain code
- email_task: read, search, draft, send emails
- browser_task: search web, open URL, summarize page
- calendar_task: list, create, update calendar events
- file_task: read, write, search, organize files
- terminal_task: run shell commands, explain output
- research_task: multi-step research, gather information
- multi_agent: requires multiple agents working together

User message: "{message}"

Reply with a JSON object: {{"intent": "...", "confidence": 0.0-1.0, "entities": []}}
Only return valid JSON, nothing else."""


class IntentResult(BaseModel):
    intent: str
    confidence: float
    entities: list[str] = []


def _keyword_fallback(user_message: str) -> IntentResult:
    msg = user_message.lower()
    if any(w in msg for w in ["code", "function", "class", "debug", "error", "script", "python", "javascript"]):
        return IntentResult(intent="coding_task", confidence=0.7)
    if any(w in msg for w in ["email", "mail", "inbox", "reply"]):
        return IntentResult(intent="email_task", confidence=0.7)
    if any(w in msg for w in ["search", "google", "website", "url", "browse"]):
        return IntentResult(intent="browser_task", confidence=0.7)
    if any(w in msg for w in ["calendar", "event", "meeting", "schedule"]):
        return IntentResult(intent="calendar_task", confidence=0.7)
    if any(w in msg for w in ["file", "folder", "document", "summarize"]):
        return IntentResult(intent="file_task", confidence=0.7)
    if any(w in msg for w in ["run", "execute", "command", "terminal", "shell"]):
        return IntentResult(intent="terminal_task", confidence=0.7)
    if any(w in msg for w in ["research", "investigate", "gather", "find out"]):
        return IntentResult(intent="research_task", confidence=0.7)
    return IntentResult(intent="simple_chat", confidence=0.6)


async def classify_intent(user_message: str) -> IntentResult:
    from models.ollama_client import OllamaClient
    from config import settings

    ollama = OllamaClient()

    if not await ollama.is_running():
        return _keyword_fallback(user_message)

    # Use the FAST model for classification (cheap, quick)
    from models.router import model_router, ModelRole
    fast_model = await model_router.get_model_for_role(ModelRole.FAST)

    # Verify at least one model is available
    local = await ollama.list_local()
    if not local:
        return _keyword_fallback(user_message)

    prompt = CLASSIFICATION_PROMPT.format(message=user_message[:500])
    try:
        response = await ollama.chat_complete(
            fast_model,
            [{"role": "user", "content": prompt}],
            temperature=0.0,
        )
        content = response.get("message", {}).get("content", "").strip()
        # Strip markdown fences
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
        data = json.loads(content)
        intent = data.get("intent", "simple_chat")
        if intent not in INTENT_TYPES:
            intent = "simple_chat"
        return IntentResult(
            intent=intent,
            confidence=float(data.get("confidence", 0.8)),
            entities=data.get("entities", []),
        )
    except Exception as e:
        log.debug(f"Intent classification failed: {e} — using keyword fallback")
        return _keyword_fallback(user_message)
