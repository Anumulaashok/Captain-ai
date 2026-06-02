import asyncio
import shlex
import time
import logging
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Permission, HealthStatus

log = logging.getLogger(__name__)

# Commands safe to run without user confirmation
SAFE_COMMANDS = frozenset([
    "ls", "ll", "cat", "head", "tail", "grep", "find", "pwd", "echo",
    "git", "python", "python3", "node", "npm", "pnpm", "cargo", "rustc",
    "swift", "go", "java", "mvn", "gradle", "pytest", "jest", "make",
    "brew", "pip", "uv", "which", "whereis", "env", "printenv",
    "df", "du", "top", "ps", "uptime", "uname", "sw_vers",
    "wc", "sort", "uniq", "awk", "sed", "cut", "tr", "xargs",
    "curl", "wget", "ping",
])

BLOCKED_COMMANDS = frozenset([
    "rm", "rmdir", "mv", "cp", "chmod", "chown", "sudo", "su",
    "kill", "killall", "pkill", "shutdown", "reboot", "halt",
    "dd", "mkfs", "fdisk", "diskutil", "format",
])


class Agent(AgentBase):
    id = "terminal"
    name = "Terminal Agent"
    description = "Execute approved shell commands and explain output"
    capabilities = ["run_command", "explain_output", "suggest_command"]
    required_permissions = [Permission.TERMINAL_EXECUTE]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="run_command",
                description="Run a shell command (safe commands only without confirmation)",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "cwd": {"type": "string", "description": "Working directory"},
                    },
                    "required": ["command"],
                },
                handler=self._run_command,
            ),
            Tool(
                name="explain_output",
                description="Explain the output of a terminal command",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "output": {"type": "string"},
                    },
                    "required": ["command", "output"],
                },
                handler=self._explain_output,
            ),
            Tool(
                name="suggest_command",
                description="Suggest the right shell command for a given intent",
                parameters={
                    "type": "object",
                    "properties": {"intent": {"type": "string"}},
                    "required": ["intent"],
                },
                handler=self._suggest_command,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a terminal agent. Help the user run shell commands. "
                    "Only use run_command for safe, read-only commands. "
                    "For destructive operations, explain what the command does and ask for confirmation."
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

    async def _run_command(self, command: str, cwd: str | None = None) -> str:
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"Invalid command syntax: {e}"

        base_cmd = parts[0] if parts else ""

        if base_cmd in BLOCKED_COMMANDS:
            return (
                f"⚠️  Command `{base_cmd}` is blocked for safety. "
                "Please run this manually in Terminal if you're sure."
            )

        if base_cmd not in SAFE_COMMANDS:
            return (
                f"Command `{base_cmd}` requires explicit permission. "
                f"Safe commands: {', '.join(sorted(SAFE_COMMANDS))}"
            )

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            output = stdout.decode(errors="replace")
            err = stderr.decode(errors="replace")
            result = output[:4000]
            if err:
                result += f"\nSTDERR:\n{err[:1000]}"
            return result or "(no output)"
        except asyncio.TimeoutError:
            return "Command timed out after 30 seconds"
        except Exception as e:
            return f"Error running command: {e}"

    async def _explain_output(self, command: str, output: str) -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = f"Explain the output of this command:\n`{command}`\n\nOutput:\n```\n{output[:2000]}\n```"
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
        ):
            result += token
        return result

    async def _suggest_command(self, intent: str) -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = (
            f"What shell command(s) would accomplish: '{intent}'? "
            "Provide the command and a brief explanation. macOS/zsh context."
        )
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
        ):
            result += token
        return result
