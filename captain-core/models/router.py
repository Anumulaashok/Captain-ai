"""
Model Router — selects the right model for each task type.

Role → model mapping is user-configurable via preferences.
Falls back to the active model if a role-specific model isn't downloaded.
"""
import logging
from enum import Enum

log = logging.getLogger(__name__)


class ModelRole(str, Enum):
    CHAT      = "chat"       # General conversation
    CODING    = "coding"     # Code generation, debug, review
    FAST      = "fast"       # Intent classification, quick ops
    RESEARCH  = "research"   # Deep reasoning, multi-step tasks
    VISION    = "vision"     # Image / multimodal
    EMBEDDING = "embedding"  # Vector embeddings


# Default role → Ollama model ID mapping
DEFAULT_ROLE_MODELS: dict[str, str] = {
    ModelRole.CHAT:      "qwen2.5:7b-instruct-q4_K_M",
    ModelRole.CODING:    "qwen2.5-coder:7b-instruct-q4_K_M",
    ModelRole.FAST:      "gemma2:2b-instruct-q8_0",
    ModelRole.RESEARCH:  "mistral:7b-instruct-v0.3-q5_K_M",
    ModelRole.VISION:    "llava:7b-v1.6-mistral-q4_K_M",
    ModelRole.EMBEDDING: "nomic-embed-text",
}

# Map intent types → role
INTENT_TO_ROLE: dict[str, ModelRole] = {
    "simple_chat":    ModelRole.CHAT,
    "coding_task":    ModelRole.CODING,
    "email_task":     ModelRole.CHAT,
    "browser_task":   ModelRole.CHAT,
    "calendar_task":  ModelRole.FAST,
    "file_task":      ModelRole.CHAT,
    "terminal_task":  ModelRole.FAST,
    "research_task":  ModelRole.RESEARCH,
    "multi_agent":    ModelRole.RESEARCH,
    "briefing_task":  ModelRole.CHAT,
}


class ModelRouter:
    """Resolves the best available model for a given role or intent."""

    async def _local_model_names(self) -> set[str]:
        from models.ollama_client import OllamaClient
        try:
            client = OllamaClient()
            local = await client.list_local()
            return {m["name"] for m in local}
        except Exception:
            return set()

    async def _role_models(self) -> dict[str, str]:
        """Get role→model map merged with user preferences."""
        from memory.preferences import preference_store
        user_overrides: dict = await preference_store.get("model_role_assignments") or {}
        return {**DEFAULT_ROLE_MODELS, **user_overrides}

    async def get_model_for_role(self, role: ModelRole) -> str:
        """Return the configured model for a role, falling back if not downloaded."""
        from config import settings

        role_models = await self._role_models()
        desired = role_models.get(role.value, settings.active_model_id)
        local_names = await self._local_model_names()

        # Check exact match
        if desired in local_names:
            return desired

        # Check prefix match (e.g. "qwen2.5" matches "qwen2.5:7b-instruct-q4_K_M")
        desired_base = desired.split(":")[0]
        for name in local_names:
            if name.startswith(desired_base):
                log.debug(f"Role {role}: using {name} (prefix match for {desired})")
                return name

        # Fall back to first available downloaded model
        if local_names:
            fallback = next(iter(local_names))
            log.debug(f"Role {role}: {desired} not available, falling back to {fallback}")
            return fallback

        # Nothing downloaded at all
        return settings.active_model_id

    async def get_model_for_intent(self, intent: str) -> str:
        """Resolve the best model for a given intent string."""
        role = INTENT_TO_ROLE.get(intent, ModelRole.CHAT)
        return await self.get_model_for_role(role)

    async def get_embedding_model(self) -> str | None:
        """Return the embedding model if available, else None."""
        role_models = await self._role_models()
        desired = role_models.get(ModelRole.EMBEDDING, "nomic-embed-text")
        local_names = await self._local_model_names()
        if any(desired in name for name in local_names):
            return desired
        return None

    async def set_role_model(self, role: ModelRole, ollama_model_id: str) -> None:
        """Persist a user override for a role."""
        from memory.preferences import preference_store
        current: dict = await preference_store.get("model_role_assignments") or {}
        current[role.value] = ollama_model_id
        await preference_store.set("model_role_assignments", current)
        log.info(f"Role {role.value} → {ollama_model_id}")

    async def get_all_assignments(self) -> dict[str, dict]:
        """Return full role assignment status with availability info."""
        role_models = await self._role_models()
        local_names = await self._local_model_names()

        result = {}
        for role in ModelRole:
            assigned = role_models.get(role.value, DEFAULT_ROLE_MODELS.get(role.value, ""))
            base = assigned.split(":")[0]
            is_available = any(base in name for name in local_names)
            result[role.value] = {
                "role": role.value,
                "assigned_model": assigned,
                "is_available": is_available,
                "default_model": DEFAULT_ROLE_MODELS.get(role.value, ""),
                "is_custom": assigned != DEFAULT_ROLE_MODELS.get(role.value),
            }
        return result


model_router = ModelRouter()
