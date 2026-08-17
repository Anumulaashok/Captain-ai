"""AgentBuilderAgent — creates new agents with user approval."""
import json
import logging
import re
import time
from pathlib import Path

from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission
from agents.builder.templates import AGENT_TEMPLATE, INIT_TEMPLATE
from agents.builder import git_ops

log = logging.getLogger(__name__)

REPO_AGENTS_DIR = Path(__file__).parent.parent


class Agent(AgentBase):
    id = "builder"
    name = "Agent Builder"
    description = "Builds new agents when Captain lacks capability, creates PRs for approval."
    capabilities = [
        "propose_agent_spec", "generate_agent_code", "create_agent_files",
        "register_agent", "create_pr",
    ]
    required_permissions = [Permission.FILESYSTEM_WRITE, Permission.NETWORK_FETCH]

    _pending_specs: dict[str, dict] = {}

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="propose_agent_spec",
                description="Generate a spec for a new agent based on capability description",
                parameters={
                    "type": "object",
                    "properties": {
                        "capability": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["capability", "agent_id"],
                },
                handler=self._propose_agent_spec,
            ),
            Tool(
                name="generate_agent_code",
                description="Generate agent implementation code from spec",
                parameters={
                    "type": "object",
                    "properties": {"agent_id": {"type": "string"}},
                    "required": ["agent_id"],
                },
                handler=self._generate_agent_code,
            ),
            Tool(
                name="create_agent_files",
                description="Write agent files to the codebase",
                parameters={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["agent_id"],
                },
                handler=self._create_agent_files,
            ),
            Tool(
                name="register_agent",
                description="Register the new agent in the registry",
                parameters={
                    "type": "object",
                    "properties": {"agent_id": {"type": "string"}},
                    "required": ["agent_id"],
                },
                handler=self._register_agent,
            ),
            Tool(
                name="create_pr",
                description="Create git branch, commit, push, and open PR",
                parameters={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["agent_id"],
                },
                handler=self._create_pr,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the Agent Builder. When Captain needs a new capability, "
                    "propose a spec, get user approval via create_agent_files(approved=true), "
                    "then register and create a PR."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)
        return AgentResult(
            task_id=task.id,
            success=bool(response),
            response=response or "",
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _propose_agent_spec(
        self, capability: str, agent_id: str, description: str = ""
    ) -> str:
        agent_id = re.sub(r"[^a-z0-9_]", "", agent_id.lower().replace(" ", "_"))
        spec = {
            "agent_id": agent_id,
            "name": agent_id.replace("_", " ").title(),
            "capability": capability,
            "description": description or f"Handles {capability} tasks",
            "integrations": [],
            "permissions": ["network:fetch"],
        }
        self._pending_specs[agent_id] = spec

        from security.approvals import approval_manager
        approved = await approval_manager.request_build_approval(
            agent_id=agent_id,
            spec=spec,
        )

        if not approved:
            return f"User declined building agent '{agent_id}'. You can build it manually."

        return json.dumps(spec, indent=2)

    async def _generate_agent_code(self, agent_id: str) -> str:
        spec = self._pending_specs.get(agent_id, {})
        if not spec:
            return f"No spec found for {agent_id}. Call propose_agent_spec first."

        code = AGENT_TEMPLATE.format(
            agent_id=agent_id,
            agent_name=spec.get("name", agent_id),
            description=spec.get("description", ""),
            capabilities=json.dumps([spec.get("capability", "general")]),
            permissions=json.dumps(
                [f"Permission.{p.upper().replace(':', '_')}" for p in spec.get("permissions", [])]
            ).replace('"Permission.', "").replace('"', ""),  # simplified
            integrations=json.dumps(spec.get("integrations", [])),
        )
        # Fix permissions to valid Python
        perms = spec.get("permissions", ["network:fetch"])
        perm_str = ", ".join(f'Permission.{p.upper().replace(":", "_")}' for p in perms if ":" in p)
        if not perm_str:
            perm_str = "Permission.NETWORK_FETCH"
        code = AGENT_TEMPLATE.format(
            agent_id=agent_id,
            agent_name=spec.get("name", agent_id),
            description=spec.get("description", ""),
            capabilities=json.dumps([spec.get("capability", "general")]),
            permissions=f"[{perm_str}]",
            integrations=json.dumps(spec.get("integrations", [])),
        )
        spec["code"] = code
        self._pending_specs[agent_id] = spec
        return f"Generated code for {agent_id} ({len(code)} chars)"

    async def _create_agent_files(self, agent_id: str, approved: bool = False) -> str:
        if not approved:
            from security.approvals import approval_manager
            approved = await approval_manager.request_build_approval(
                agent_id=agent_id,
                spec=self._pending_specs.get(agent_id, {}),
            )
        if not approved:
            return "Build not approved."

        spec = self._pending_specs.get(agent_id)
        if not spec or "code" not in spec:
            await self._generate_agent_code(agent_id)
            spec = self._pending_specs.get(agent_id, {})

        agent_dir = REPO_AGENTS_DIR / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "__init__.py").write_text(INIT_TEMPLATE.format(agent_id=agent_id))
        (agent_dir / "agent.py").write_text(spec.get("code", ""))

        await self._update_registry(agent_id)
        return f"Created files at captain-core/agents/{agent_id}/"

    async def _register_agent(self, agent_id: str) -> str:
        from agents.registry import agent_registry
        ok = agent_registry.register_dynamic(agent_id)
        return f"Registered {agent_id}" if ok else f"Failed to register {agent_id}"

    async def _create_pr(self, agent_id: str, approved: bool = False) -> str:
        if not approved:
            from security.approvals import approval_manager
            approved = await approval_manager.request_merge_approval(
                agent_id=agent_id,
                pr_title=f"Add {agent_id} agent",
            )
        if not approved:
            return "PR creation not approved."

        branch = git_ops.create_feature_branch(agent_id)
        if not git_ops.commit_agent_files(agent_id):
            return "Nothing to commit or commit failed."
        if not git_ops.push_branch(branch):
            return f"Branch {branch} created locally. Push failed — check git remote."

        result = git_ops.create_pull_request(
            branch,
            title=f"feat: add {agent_id} agent",
            body=f"Auto-generated by Captain AgentBuilder.\n\nAgent: {agent_id}",
        )
        if result.get("success"):
            return (
                f"PR created: {result.get('url')}\n"
                "Please review and merge when ready."
            )
        return f"PR creation failed: {result.get('error')}"

    async def _update_registry(self, agent_id: str) -> None:
        registry_path = REPO_AGENTS_DIR.parent / "registry.py"
        content = registry_path.read_text()
        entry = f'    "{agent_id}":   "agents.{agent_id}.agent",\n'
        if f'"{agent_id}"' not in content:
            content = content.replace(
                "AGENT_MODULES = {",
                f"AGENT_MODULES = {{\n{entry}",
            )
            registry_path.write_text(content)
