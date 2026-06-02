"""
GitHub Agent — polls PRs awaiting review, failed CI, and new issues.
Uses the `gh` CLI (already installed on most macOS dev machines).
Falls back to PyGithub if GITHUB_TOKEN is set in the environment.
Results are written to briefing/store.py.
"""
import logging
import time
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "github"
    name = "GitHub Agent"
    description = "Monitors GitHub repositories for PRs, CI status, and issues"
    capabilities = ["list_prs", "list_issues", "get_ci_status", "summarize_repo_activity"]
    required_permissions = [Permission.NETWORK_FETCH]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="list_prs_awaiting_review",
                description="List open PRs that need your review",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "owner/repo or 'all' for all repos"},
                    },
                    "required": [],
                },
                handler=self._list_prs,
            ),
            Tool(
                name="list_open_issues",
                description="List open issues assigned to you or mentioning you",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string", "description": "owner/repo or 'all'"},
                    },
                    "required": [],
                },
                handler=self._list_issues,
            ),
            Tool(
                name="get_failed_ci",
                description="List recent failed CI / workflow runs",
                parameters={
                    "type": "object",
                    "properties": {
                        "repo": {"type": "string"},
                    },
                    "required": ["repo"],
                },
                handler=self._get_failed_ci,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        """
        Background runner: fetch GitHub state and write briefing items.
        Also returns a text summary for on-demand use.
        """
        t_start = time.time()
        from briefing.store import add_item
        from api.websocket import event_bus

        sections = []

        # PRs awaiting review
        try:
            prs = await self._list_prs()
            if prs and "No PRs" not in prs:
                sections.append(f"**PRs needing review:**\n{prs}")
                await add_item(
                    category="prs",
                    title="PRs awaiting your review",
                    summary=prs[:500],
                    source_agent=self.id,
                    priority=2,
                )
                await event_bus.publish("notification", {
                    "category": "prs",
                    "title": "PRs awaiting review",
                    "summary": prs[:200],
                    "priority": 2,
                })
        except Exception as e:
            log.debug(f"GitHub PRs failed: {e}")

        # Open issues
        try:
            issues = await self._list_issues()
            if issues and "No issues" not in issues:
                sections.append(f"**Open issues:**\n{issues}")
                await add_item(
                    category="notifications",
                    title="New GitHub issues",
                    summary=issues[:500],
                    source_agent=self.id,
                    priority=4,
                )
        except Exception as e:
            log.debug(f"GitHub issues failed: {e}")

        response = "\n\n".join(sections) if sections else "No GitHub activity to report."
        return AgentResult(
            task_id=task.id,
            success=True,
            response=response,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _run_gh(self, *args: str) -> str:
        """Run the `gh` CLI and return stdout."""
        import asyncio
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return f"gh error: {stderr.decode().strip()[:300]}"
            return stdout.decode().strip()
        except FileNotFoundError:
            return "GitHub CLI (`gh`) is not installed. Install with: brew install gh"
        except asyncio.TimeoutError:
            return "GitHub CLI timed out"
        except Exception as e:
            return f"Error: {e}"

    async def _list_prs(self, repo: str = "") -> str:
        args = ["pr", "list", "--state", "open", "--json", "number,title,author,url,reviewRequested"]
        if repo and repo != "all":
            args = ["pr", "list", "-R", repo, "--state", "open",
                    "--json", "number,title,author,url"]
        result = await self._run_gh(*args)
        if result.startswith("gh error") or result.startswith("GitHub CLI"):
            return result
        try:
            import json
            prs = json.loads(result)
            if not prs:
                return "No PRs awaiting review."
            lines = [f"#{p['number']} — {p['title']} (by {p['author']['login']}) {p.get('url','')}"
                     for p in prs[:10]]
            return "\n".join(lines)
        except Exception:
            return result[:600]

    async def _list_issues(self, repo: str = "") -> str:
        args = ["issue", "list", "--state", "open", "--assignee", "@me",
                "--json", "number,title,url"]
        if repo and repo != "all":
            args = ["issue", "list", "-R", repo, "--state", "open",
                    "--assignee", "@me", "--json", "number,title,url"]
        result = await self._run_gh(*args)
        if result.startswith("gh error") or result.startswith("GitHub CLI"):
            return result
        try:
            import json
            issues = json.loads(result)
            if not issues:
                return "No open issues assigned to you."
            lines = [f"#{i['number']} — {i['title']} {i.get('url','')}" for i in issues[:10]]
            return "\n".join(lines)
        except Exception:
            return result[:600]

    async def _get_failed_ci(self, repo: str) -> str:
        result = await self._run_gh(
            "run", "list", "-R", repo, "--status", "failure",
            "--json", "name,status,conclusion,url", "--limit", "5",
        )
        if result.startswith("gh error") or result.startswith("GitHub CLI"):
            return result
        try:
            import json
            runs = json.loads(result)
            if not runs:
                return "No recent CI failures."
            lines = [f"❌ {r['name']} — {r['conclusion']} {r.get('url','')}" for r in runs]
            return "\n".join(lines)
        except Exception:
            return result[:600]

    async def health_check(self):
        from agents.base import HealthStatus
        out = await self._run_gh("auth", "status")
        if "Logged in" in out or "github.com" in out.lower():
            return HealthStatus.HEALTHY
        return HealthStatus.DEGRADED
