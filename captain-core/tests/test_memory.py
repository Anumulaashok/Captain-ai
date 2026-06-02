"""Memory system tests."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from memory.schemas import MemoryEntrySchema, ConversationContext, MessageContext


def test_memory_entry_schema():
    entry = MemoryEntrySchema(type="fact", value="User prefers Python over JavaScript")
    assert entry.id != ""
    assert entry.confidence == 1.0
    assert entry.type == "fact"


def test_conversation_context_empty():
    ctx = ConversationContext(conversation_id="test-id")
    assert ctx.recent_messages == []
    assert ctx.retrieved_memories == []


@pytest.mark.asyncio
async def test_preference_store_defaults():
    """Preferences return defaults when DB not available."""
    from memory.preferences import PreferenceStore, DEFAULTS
    store = PreferenceStore()

    with patch.object(store, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = DEFAULTS.get("ui_theme")
        value = await store.get("ui_theme")
        assert value == "system"


@pytest.mark.asyncio
async def test_memory_manager_build_system_prompt():
    from memory.manager import MemoryManager
    from memory.schemas import MemoryEntrySchema

    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_prefs = MagicMock()

    manager = MemoryManager(
        episodic=mock_episodic,
        semantic=mock_semantic,
        preferences=mock_prefs,
    )

    ctx = ConversationContext(
        conversation_id="test",
        user_preferences={"ui_theme": "dark"},
        retrieved_memories=[
            MemoryEntrySchema(type="fact", value="User is a Python developer"),
        ],
    )
    prompt = manager.build_system_prompt(ctx)
    assert "Captain" in prompt
    assert "Python developer" in prompt


@pytest.mark.asyncio
async def test_memory_manager_build_messages():
    from memory.manager import MemoryManager

    mock_episodic = MagicMock()
    mock_semantic = MagicMock()
    mock_prefs = MagicMock()
    manager = MemoryManager(mock_episodic, mock_semantic, mock_prefs)

    ctx = ConversationContext(
        conversation_id="test",
        recent_messages=[
            MessageContext(role="user", content="Hello"),
            MessageContext(role="assistant", content="Hi there!"),
        ],
    )
    messages = manager.build_messages(ctx, "How are you?")
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "How are you?"
    assert len(messages) == 4  # system + 2 history + user
