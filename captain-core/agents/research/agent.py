import time
import logging
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission, HealthStatus

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "research"
    name = "Research Agent"
    description = "Multi-step web research with memory storage and report generation"
    capabilities = ["web_search", "fetch_url", "synthesize_findings", "save_to_memory", "create_report"]
    required_permissions = [Permission.NETWORK_FETCH, Permission.FILESYSTEM_WRITE]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="web_search",
                description="Search the web for information",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "num_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                handler=self._web_search,
            ),
            Tool(
                name="fetch_and_extract",
                description="Fetch a URL and extract key facts",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "focus": {"type": "string"},
                    },
                    "required": ["url"],
                },
                handler=self._fetch_and_extract,
            ),
            Tool(
                name="save_finding",
                description="Save a research finding to long-term memory",
                parameters={
                    "type": "object",
                    "properties": {
                        "key": {"type": "string"},
                        "finding": {"type": "string"},
                    },
                    "required": ["key", "finding"],
                },
                handler=self._save_finding,
            ),
            Tool(
                name="write_report",
                description="Write research findings to a markdown file",
                parameters={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "filename": {"type": "string"},
                    },
                    "required": ["title", "content", "filename"],
                },
                handler=self._write_report,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a research agent. Conduct thorough multi-step research using web searches. "
                    "For each query: search → fetch top results → extract facts → synthesize. "
                    "Always cite sources with URLs. Save important findings to memory."
                ),
            },
            {"role": "user", "content": task.user_message},
        ]
        response, tool_calls, tokens = await self._llm_tool_loop(messages, tools, task)

        # Extract any written reports as artifacts
        artifacts = []
        for tc in tool_calls:
            if tc.tool_name == "write_report" and tc.result and "Written" in tc.result:
                path = tc.arguments.get("filename", "research.md")
                artifacts.append(Artifact(
                    type="file",
                    name=tc.arguments.get("title", "Research Report"),
                    content=tc.arguments.get("content", ""),
                    path=path,
                    mime_type="text/markdown",
                ))

        return AgentResult(
            task_id=task.id,
            success=True,
            response=response,
            artifacts=artifacts,
            tool_calls=tool_calls,
            tokens_used=tokens,
            latency_ms=int((time.time() - t_start) * 1000),
        )

    async def _web_search(self, query: str, num_results: int = 5) -> str:
        import httpx
        from bs4 import BeautifulSoup
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
                r = await client.get(url)
            soup = BeautifulSoup(r.text, "lxml")
            results = []
            for i, result in enumerate(soup.select(".result__body")[:num_results]):
                title = result.select_one(".result__title")
                href_el = result.select_one(".result__url")
                snippet = result.select_one(".result__snippet")
                t = title.get_text(strip=True) if title else ""
                h = href_el.get_text(strip=True) if href_el else ""
                s = snippet.get_text(strip=True) if snippet else ""
                results.append(f"[{i+1}] {t}\n    {h}\n    {s}")
            return "\n\n".join(results) or "No results found"
        except Exception as e:
            return f"Search error: {e}"

    async def _fetch_and_extract(self, url: str, focus: str = "") -> str:
        import httpx
        from bs4 import BeautifulSoup
        from models.ollama_client import OllamaClient
        from config import settings
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
                r = await client.get(url)
            soup = BeautifulSoup(r.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)[:4000]
        except Exception as e:
            return f"Failed to fetch {url}: {e}"

        prompt = (
            f"Extract key facts from this webpage{' about: ' + focus if focus else ''}:\n\n{text}"
        )
        result = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=600,
        ):
            result += token
        return f"Facts from {url}:\n{result}"

    async def _save_finding(self, key: str, finding: str) -> str:
        from memory.manager import memory_manager
        await memory_manager.store_memory("fact", finding, key=key, source="research_agent")
        return f"Saved: {key}"

    async def _write_report(self, title: str, content: str, filename: str) -> str:
        from pathlib import Path
        from datetime import datetime
        home = Path.home()
        reports_dir = home / "Documents" / "Captain" / "Research"
        reports_dir.mkdir(parents=True, exist_ok=True)
        path = reports_dir / filename
        full_content = f"# {title}\n\n*Generated by Captain AI — {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n{content}"
        path.write_text(full_content)
        return f"Written to {path}"
