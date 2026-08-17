"""Auto-improvement suggestions for failing agents."""
import logging

log = logging.getLogger(__name__)


class ImprovementEngine:
    FAILURE_THRESHOLD = 0.3  # suggest improvements below 70% success

    async def analyze_failures(self, agent_id: str) -> dict | None:
        from metrics.tracker import metrics_tracker

        stats = await metrics_tracker.get_agent_stats(agent_id)
        if stats["total_runs"] < 5:
            return None
        if stats["success_rate"] >= (1 - self.FAILURE_THRESHOLD):
            return None

        return {
            "agent_id": agent_id,
            "success_rate": stats["success_rate"],
            "error_patterns": stats.get("error_patterns", []),
            "suggestion": self._generate_suggestion(agent_id, stats),
        }

    def _generate_suggestion(self, agent_id: str, stats: dict) -> str:
        patterns = stats.get("error_patterns", [])
        if patterns:
            top_error = patterns[0][0]
            return (
                f"The {agent_id} agent fails {int((1 - stats['success_rate']) * 100)}% "
                f"of the time. Top error: '{top_error}'. "
                f"Consider updating the agent code or adding better error handling."
            )
        return (
            f"The {agent_id} agent has a low success rate "
            f"({int(stats['success_rate'] * 100)}%). Review recent failures."
        )

    async def get_suggestions(self) -> list[dict]:
        from agents.registry import agent_registry
        suggestions = []
        for agent in agent_registry.list_all():
            analysis = await self.analyze_failures(agent.id)
            if analysis:
                suggestions.append(analysis)
        return suggestions

    async def propose_pr_for_improvement(self, agent_id: str) -> str:
        """Route to AgentBuilder for code improvements."""
        analysis = await self.analyze_failures(agent_id)
        if not analysis:
            return f"No improvement needed for {agent_id}."
        return (
            f"I've analyzed {agent_id} and found issues. "
            f"{analysis['suggestion']} "
            "Would you like me to create a PR with improvements?"
        )


improvement_engine = ImprovementEngine()
