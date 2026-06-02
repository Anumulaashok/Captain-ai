import time
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission, HealthStatus


class Agent(AgentBase):
    id = "coding"
    name = "Coding Agent"
    description = "Generate, debug, review and explain code in any language"
    capabilities = ["generate_code", "debug_code", "review_code", "explain_code", "run_tests"]
    required_permissions = [Permission.FILESYSTEM_READ, Permission.FILESYSTEM_WRITE]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="generate_code",
                description="Generate code in a specified language based on requirements",
                parameters={
                    "type": "object",
                    "properties": {
                        "language": {"type": "string", "description": "Programming language"},
                        "spec": {"type": "string", "description": "What the code should do"},
                        "style": {"type": "string", "description": "coding style or framework"},
                    },
                    "required": ["language", "spec"],
                },
                handler=self._generate_code,
            ),
            Tool(
                name="debug_code",
                description="Analyze code and an error message to find and fix the bug",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "error": {"type": "string"},
                        "language": {"type": "string"},
                    },
                    "required": ["code", "error"],
                },
                handler=self._debug_code,
            ),
            Tool(
                name="review_code",
                description="Review code for bugs, style, security issues and improvements",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "language": {"type": "string"},
                        "focus": {"type": "string", "description": "security | performance | style | all"},
                    },
                    "required": ["code"],
                },
                handler=self._review_code,
            ),
            Tool(
                name="explain_code",
                description="Explain what a piece of code does in plain English",
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "detail_level": {"type": "string", "description": "brief | detailed"},
                    },
                    "required": ["code"],
                },
                handler=self._explain_code,
            ),
            Tool(
                name="read_file",
                description="Read the contents of a source code file",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                handler=self._read_file,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert software engineer. Use the provided tools to help the user "
                    "with coding tasks. Always write clean, well-structured code with no unnecessary comments."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]

        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)

        # Extract code artifacts from response
        artifacts = self._extract_code_blocks(response)

        return AgentResult(
            task_id=task.id,
            success=True,
            response=response,
            artifacts=artifacts,
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus.HEALTHY

    # ── Tool handlers ─────────────────────────────────────────────────

    async def _generate_code(self, language: str, spec: str, style: str = "") -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = f"Write {language} code that: {spec}"
        if style:
            prompt += f"\nStyle/framework: {style}"
        prompt += "\nReturn only the code, no explanation."
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        ):
            result += token
        return result

    async def _debug_code(self, code: str, error: str, language: str = "") -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = (
            f"Debug this {'`' + language + '`' if language else ''} code.\n"
            f"Error: {error}\n\nCode:\n```\n{code}\n```\n\n"
            "Identify the bug and return the fixed code."
        )
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.1,
        ):
            result += token
        return result

    async def _review_code(self, code: str, language: str = "", focus: str = "all") -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = (
            f"Review this code for {focus} issues.\n```\n{code}\n```\n"
            "List issues clearly with line numbers where possible."
        )
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
        ):
            result += token
        return result

    async def _explain_code(self, code: str, detail_level: str = "detailed") -> str:
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = (
            f"Explain this code {'briefly' if detail_level == 'brief' else 'in detail'}:\n```\n{code}\n```"
        )
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
        ):
            result += token
        return result

    async def _read_file(self, path: str) -> str:
        from pathlib import Path
        p = Path(path).expanduser()
        if not p.exists():
            return f"File not found: {path}"
        if p.stat().st_size > 500_000:
            return "File too large (>500 KB)"
        return p.read_text(errors="replace")[:8000]

    def _extract_code_blocks(self, text: str) -> list[Artifact]:
        import re
        artifacts = []
        pattern = r"```(\w+)?\n(.*?)```"
        for match in re.finditer(pattern, text, re.DOTALL):
            lang = match.group(1) or "text"
            code = match.group(2).strip()
            if len(code) > 10:
                artifacts.append(Artifact(
                    type="code",
                    name=f"code.{lang}",
                    content=code,
                    mime_type=f"text/x-{lang}",
                ))
        return artifacts
