"""Unified memory facade — retrieves and consolidates context from all sources."""
import logging
from datetime import datetime

from memory.episodic import episodic_memory, EpisodicMemory
from memory.semantic import semantic_memory, SemanticMemory
from memory.preferences import preference_store, PreferenceStore
from memory.schemas import MemoryEntrySchema, ConversationContext

log = logging.getLogger(__name__)

# Token budget allocation (fits 7B model with 4096 context)
BUDGET = {
    "system_prompt": 200,
    "preferences": 100,
    "semantic_memories": 500,
    "conversation_history": 1500,
    "user_message": 500,
}


class MemoryManager:
    def __init__(
        self,
        episodic: EpisodicMemory = episodic_memory,
        semantic: SemanticMemory = semantic_memory,
        preferences: PreferenceStore = preference_store,
    ):
        self.episodic = episodic
        self.semantic = semantic
        self.preferences = preferences

    async def retrieve_context(
        self, query: str, conversation_id: str
    ) -> ConversationContext:
        """Build full context for an LLM call."""
        recent = await self.episodic.get_recent_messages(conversation_id, n=20)
        try:
            semantic_results = await self.semantic.search(query, k=5)
        except Exception as e:
            log.debug(f"Semantic search skipped: {e}")
            from memory.schemas import RetrievalResult
            semantic_results = RetrievalResult(memories=[], scores=[], query=query)
        prefs = await self.preferences.get_all()

        # Trim semantic results to budget
        trimmed_memories = []
        token_count = 0
        for mem, score in zip(semantic_results.memories, semantic_results.scores):
            est_tokens = len(mem.value.split()) + 20
            if token_count + est_tokens > BUDGET["semantic_memories"]:
                break
            if score > 0.65:  # only include relevant memories
                trimmed_memories.append(mem)
                token_count += est_tokens

        return ConversationContext(
            conversation_id=conversation_id,
            recent_messages=recent,
            retrieved_memories=trimmed_memories,
            user_preferences=prefs,
        )

    def build_system_prompt(self, context: ConversationContext) -> str:
        """Assemble system prompt injecting memory and preferences."""
        lines = [
            "You are Captain, a helpful, local AI assistant running on macOS.",
            "You are private, fast, and fully offline.",
            "",
        ]

        # Preferences
        prefs = context.user_preferences
        if theme := prefs.get("ui_theme"):
            lines.append(f"UI preference: {theme} mode.")

        # Long-term memories
        if context.retrieved_memories:
            lines.append("\nRelevant things I remember about you:")
            for mem in context.retrieved_memories:
                lines.append(f"- {mem.value}")

        lines.append(
            "\nAlways be concise. Format code in markdown code blocks. "
            "If you use an agent or tool, explain what you're doing briefly."
        )
        return "\n".join(lines)

    def build_messages(
        self, context: ConversationContext, user_message: str
    ) -> list[dict]:
        """Build the messages list for an LLM call."""
        system_prompt = self.build_system_prompt(context)
        messages = [{"role": "system", "content": system_prompt}]
        for msg in context.recent_messages:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": user_message})
        return messages

    async def store_memory(
        self,
        type: str,
        value: str,
        key: str | None = None,
        source: str | None = None,
    ) -> str:
        """Store a memory entry in both PostgreSQL and Pinecone."""
        from db.database import AsyncSessionLocal
        from db.models import MemoryEntry as MemoryEntryORM

        entry = MemoryEntrySchema(type=type, key=key, value=value, source=source)

        # Store in Pinecone for semantic search
        pinecone_id = await self.semantic.store(entry)
        entry.pinecone_id = pinecone_id

        # Store in PostgreSQL for structured queries
        async with AsyncSessionLocal() as db:
            orm_entry = MemoryEntryORM(
                id=entry.id,
                type=entry.type,
                key=entry.key,
                value=entry.value,
                source=entry.source,
                pinecone_id=pinecone_id,
                confidence=entry.confidence,
                created_at=entry.created_at,
            )
            db.add(orm_entry)
            await db.commit()

        return entry.id

    async def consolidate(self, conversation_id: str) -> None:
        """
        After N messages, extract key facts and store as long-term memories.
        Called automatically after threshold is reached.
        """
        from models.ollama_client import OllamaClient
        from config import settings

        messages = await self.episodic.get_recent_messages(conversation_id, n=30)
        if len(messages) < 5:
            return

        # Ask LLM to extract facts
        conversation_text = "\n".join(
            f"{m.role}: {m.content}" for m in messages[-20:]
        )
        extraction_prompt = (
            "Extract 3-5 important facts or preferences the user revealed in this conversation. "
            "Return each on a new line starting with '- '. Be concise.\n\n"
            + conversation_text
        )

        ollama = OllamaClient()
        if not await ollama.is_running():
            return

        result_text = ""
        async for token in ollama.chat(
            settings.active_model_id,
            [{"role": "user", "content": extraction_prompt}],
            max_tokens=300,
            temperature=0.2,
        ):
            result_text += token

        facts = [
            line.lstrip("- ").strip()
            for line in result_text.split("\n")
            if line.strip().startswith("-") and len(line) > 5
        ]

        for fact in facts:
            await self.store_memory("fact", fact, source=conversation_id)

        # Store conversation summary in Pinecone
        summary_prompt = (
            f"Summarize this conversation in 2-3 sentences:\n\n{conversation_text}"
        )
        summary = ""
        async for token in ollama.chat(
            settings.active_model_id,
            [{"role": "user", "content": summary_prompt}],
            max_tokens=150,
            temperature=0.2,
        ):
            summary += token

        if summary.strip():
            await self.semantic.store_conversation_summary(conversation_id, summary.strip())

        log.info(f"Memory consolidated for conversation {conversation_id}: {len(facts)} facts")


memory_manager = MemoryManager()
