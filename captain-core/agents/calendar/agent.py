import subprocess
import time
import logging
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Permission, HealthStatus

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "calendar"
    name = "Calendar Agent"
    description = "Create, update and query calendar events via macOS Calendar"
    capabilities = ["list_events", "create_event", "update_event", "find_free_time"]
    required_permissions = [Permission.CALENDAR_READ, Permission.CALENDAR_WRITE]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="list_events",
                description="List upcoming calendar events",
                parameters={
                    "type": "object",
                    "properties": {
                        "days_ahead": {"type": "integer", "default": 7},
                        "calendar_name": {"type": "string", "default": ""},
                    },
                    "required": [],
                },
                handler=self._list_events,
            ),
            Tool(
                name="create_event",
                description="Create a new calendar event",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start_date": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
                        "end_date": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
                        "notes": {"type": "string"},
                        "calendar_name": {"type": "string", "default": ""},
                    },
                    "required": ["title", "start_date", "end_date"],
                },
                handler=self._create_event,
            ),
            Tool(
                name="find_free_time",
                description="Find free time slots in the calendar",
                parameters={
                    "type": "object",
                    "properties": {
                        "duration_hours": {"type": "number", "default": 1.0},
                        "within_days": {"type": "integer", "default": 7},
                    },
                    "required": [],
                },
                handler=self._find_free_time,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a calendar agent. Help the user manage their schedule. "
                    "When creating events, confirm the details with the user before proceeding."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)
        return AgentResult(
            task_id=task.id,
            success=True,
            response=response,
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def health_check(self) -> HealthStatus:
        script = 'tell application "Calendar" to return name of first calendar'
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=5
            )
            return HealthStatus.HEALTHY if result.returncode == 0 else HealthStatus.DEGRADED
        except Exception:
            return HealthStatus.UNHEALTHY

    async def _list_events(self, days_ahead: int = 7, calendar_name: str = "") -> str:
        # AppleScript to list events in the next N days
        cal_filter = f'calendar "{calendar_name}" of ' if calendar_name else ""
        script = f"""
        tell application "Calendar"
            set today to current date
            set endDate to today + ({days_ahead} * days)
            set evts to (every event of {cal_filter}calendars whose start date >= today and start date <= endDate)
            set result to ""
            repeat with e in evts
                set result to result & summary of e & " — " & (start date of e as string) & "\\n"
            end repeat
            return result
        end tell
        """
        try:
            r = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=15
            )
            return r.stdout.strip() or "No events in the next " + str(days_ahead) + " days"
        except Exception as e:
            return f"Error: {e}"

    async def _create_event(
        self, title: str, start_date: str, end_date: str,
        notes: str = "", calendar_name: str = ""
    ) -> str:
        cal_target = f'calendar "{calendar_name}" of ' if calendar_name else "first calendar of "
        script = f"""
        tell application "Calendar"
            set newEvent to make new event at end of events of {cal_target}calendars
            set summary of newEvent to "{title}"
            set start date of newEvent to date "{start_date}"
            set end date of newEvent to date "{end_date}"
            {"set description of newEvent to \"" + notes + "\"" if notes else ""}
            save
        end tell
        """
        try:
            r = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=15
            )
            if r.returncode == 0:
                return f"Created event: '{title}' on {start_date}"
            return f"Failed to create event: {r.stderr}"
        except Exception as e:
            return f"Error: {e}"

    async def _find_free_time(self, duration_hours: float = 1.0, within_days: int = 7) -> str:
        events_text = await self._list_events(within_days)
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = (
            f"Given these calendar events:\n{events_text}\n\n"
            f"Find {duration_hours}-hour free slots in the next {within_days} days "
            "(9 AM–6 PM). List them clearly."
        )
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
        ):
            result += token
        return result
