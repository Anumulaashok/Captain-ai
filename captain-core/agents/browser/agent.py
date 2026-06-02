import time
import logging
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission, HealthStatus

log = logging.getLogger(__name__)


class Agent(AgentBase):
    id = "browser"
    name = "Browser Agent"
    description = "Search the web, open URLs, and summarize pages"
    capabilities = ["search_web", "open_url", "get_page_content", "summarize_page"]
    required_permissions = [Permission.NETWORK_FETCH, Permission.BROWSER_OPEN]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="search_web",
                description="Search the web using DuckDuckGo and return top results",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "max_results": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
                handler=self._search_web,
            ),
            Tool(
                name="get_page_content",
                description="Fetch and extract readable text content from a URL",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                handler=self._get_page_content,
            ),
            Tool(
                name="summarize_page",
                description="Fetch a URL and return a summary of its content",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "focus": {"type": "string", "description": "What aspect to focus on"},
                    },
                    "required": ["url"],
                },
                handler=self._summarize_page,
            ),
            Tool(
                name="open_in_browser",
                description="Open a URL in the default macOS browser",
                parameters={
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
                handler=self._open_in_browser,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a browser agent. Use tools to search the web and fetch page content. "
                    "Always cite your sources with URLs."
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
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get("https://duckduckgo.com")
            return HealthStatus.HEALTHY
        except Exception:
            return HealthStatus.DEGRADED

    # ── Tool handlers ─────────────────────────────────────────────────

    async def _search_web(self, query: str, max_results: int = 5) -> str:
        import httpx
        from bs4 import BeautifulSoup
        url = f"https://html.duckduckgo.com/html/?q={query}"
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        async with httpx.AsyncClient(timeout=15.0, headers=headers, follow_redirects=True) as client:
            r = await client.get(url)
        soup = BeautifulSoup(r.text, "lxml")
        results = []
        for i, result in enumerate(soup.select(".result__body")[:max_results]):
            title_el = result.select_one(".result__title")
            url_el = result.select_one(".result__url")
            snippet_el = result.select_one(".result__snippet")
            title = title_el.get_text(strip=True) if title_el else ""
            href = url_el.get_text(strip=True) if url_el else ""
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""
            results.append(f"{i+1}. {title}\n   URL: {href}\n   {snippet}")
        return "\n\n".join(results) if results else "No results found"

    async def _get_page_content(self, url: str) -> str:
        import httpx
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        async with httpx.AsyncClient(timeout=20.0, headers=headers, follow_redirects=True) as client:
            r = await client.get(url)
        soup = BeautifulSoup(r.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:6000]

    async def _summarize_page(self, url: str, focus: str = "") -> str:
        content = await self._get_page_content(url)
        if not content:
            return "Could not fetch page content"
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = f"Summarize this page content{' focusing on: ' + focus if focus else ''}:\n\n{content[:3000]}"
        summary = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        ):
            summary += token
        return f"Summary of {url}:\n{summary}"

    async def _open_in_browser(self, url: str) -> str:
        import subprocess
        subprocess.Popen(["open", url])
        return f"Opened {url} in browser"
