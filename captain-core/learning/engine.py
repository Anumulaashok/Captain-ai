"""Learning engine — observes interactions and infers preferences."""
import logging

from learning import logger as interaction_logger
from learning.adaptation import adapt_response
from learning.preferences import infer_communication_style, infer_sender_importance

log = logging.getLogger(__name__)


class LearningEngine:
    async def observe(
        self,
        user_message: str,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        accepted: bool | None = None,
        feedback: str | None = None,
    ) -> None:
        await interaction_logger.log_interaction(
            user_message=user_message,
            agent_id=agent_id,
            conversation_id=conversation_id,
            accepted=accepted,
            feedback=feedback,
        )

    async def infer_preference(self, category: str) -> dict:
        if category == "communication":
            return await infer_communication_style()
        if category == "senders":
            return await infer_sender_importance()
        return {}

    async def adapt_response(self, response: str) -> str:
        return await adapt_response(response)

    async def record_feedback(
        self, conversation_id: str, rating: int, comment: str = ""
    ) -> None:
        from memory.preferences import preference_store
        feedback_history = await preference_store.get("feedback_history") or []
        feedback_history.append({
            "conversation_id": conversation_id,
            "rating": rating,
            "comment": comment,
        })
        await preference_store.set("feedback_history", feedback_history[-100:])


learning_engine = LearningEngine()
