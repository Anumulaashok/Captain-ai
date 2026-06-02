import time
import logging
from pathlib import Path
from agents.base import AgentBase, AgentTask, AgentResult, Tool, Artifact, Permission, HealthStatus

log = logging.getLogger(__name__)
HOME = Path.home()


class Agent(AgentBase):
    id = "file"
    name = "File Agent"
    description = "Search, read, write and summarize local files"
    capabilities = ["search_files", "read_file", "write_file", "summarize_document", "index_directory"]
    required_permissions = [Permission.FILESYSTEM_READ, Permission.FILESYSTEM_WRITE]

    async def get_tools(self) -> list[Tool]:
        return [
            Tool(
                name="search_files",
                description="Search for files by name or content in a directory",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "path": {"type": "string", "default": "~/"},
                        "file_type": {"type": "string", "description": "e.g. .py .md .txt"},
                    },
                    "required": ["query"],
                },
                handler=self._search_files,
            ),
            Tool(
                name="read_file",
                description="Read the contents of a file",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "max_chars": {"type": "integer", "default": 8000},
                    },
                    "required": ["path"],
                },
                handler=self._read_file,
            ),
            Tool(
                name="write_file",
                description="Write content to a file (creates if not exists)",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "mode": {"type": "string", "description": "write | append", "default": "write"},
                    },
                    "required": ["path", "content"],
                },
                handler=self._write_file,
            ),
            Tool(
                name="list_directory",
                description="List files and subdirectories in a path",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                handler=self._list_directory,
            ),
            Tool(
                name="summarize_document",
                description="Read and summarize a document file (PDF, DOCX, TXT, MD)",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
                handler=self._summarize_document,
            ),
        ]

    async def run(self, task: AgentTask) -> AgentResult:
        t_start = time.time()
        tools = await self.get_tools()
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a file management agent. Help the user find, read, write and organize files. "
                    "Always confirm before writing files. Paths are relative to the user's home directory by default."
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

    def _safe_path(self, path: str) -> Path:
        """Resolve path, sandboxed to user home."""
        p = Path(path).expanduser().resolve()
        if not str(p).startswith(str(HOME)):
            raise PermissionError(f"Access outside home directory not allowed: {p}")
        return p

    async def _search_files(self, query: str, path: str = "~/", file_type: str = "") -> str:
        search_path = self._safe_path(path)
        pattern = f"*{file_type}*" if file_type else "*"
        matches = []
        for p in search_path.rglob(pattern):
            if p.is_file() and query.lower() in p.name.lower():
                matches.append(str(p))
            if len(matches) >= 20:
                break
        if not matches:
            # Try content search (slow, limit scope)
            for p in search_path.rglob("*.txt"):
                try:
                    if query.lower() in p.read_text(errors="ignore").lower():
                        matches.append(f"{p} (content match)")
                        if len(matches) >= 10:
                            break
                except Exception:
                    pass
        return "\n".join(matches) if matches else f"No files matching '{query}' found in {path}"

    async def _read_file(self, path: str, max_chars: int = 8000) -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"File not found: {path}"
        if p.suffix.lower() == ".pdf":
            return self._read_pdf(p, max_chars)
        if p.suffix.lower() == ".docx":
            return self._read_docx(p, max_chars)
        return p.read_text(errors="replace")[:max_chars]

    def _read_pdf(self, p: Path, max_chars: int) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(p))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text[:max_chars]
        except Exception as e:
            return f"Could not read PDF: {e}"

    def _read_docx(self, p: Path, max_chars: int) -> str:
        try:
            from docx import Document
            doc = Document(str(p))
            text = "\n".join(para.text for para in doc.paragraphs)
            return text[:max_chars]
        except Exception as e:
            return f"Could not read DOCX: {e}"

    async def _write_file(self, path: str, content: str, mode: str = "write") -> str:
        p = self._safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        if mode == "append":
            with p.open("a") as f:
                f.write(content)
        else:
            p.write_text(content)
        return f"Written {len(content)} chars to {p}"

    async def _list_directory(self, path: str) -> str:
        p = self._safe_path(path)
        if not p.exists():
            return f"Directory not found: {path}"
        entries = []
        for item in sorted(p.iterdir()):
            prefix = "📁 " if item.is_dir() else "📄 "
            size = f"  ({item.stat().st_size:,} bytes)" if item.is_file() else ""
            entries.append(f"{prefix}{item.name}{size}")
        return "\n".join(entries[:50]) or "(empty)"

    async def _summarize_document(self, path: str) -> str:
        content = await self._read_file(path, max_chars=4000)
        if content.startswith("File not found") or content.startswith("Could not"):
            return content
        from models.ollama_client import OllamaClient
        from config import settings
        prompt = f"Summarize this document:\n\n{content}"
        summary = ""
        async for token in OllamaClient().chat(
            settings.active_model_id,
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=500,
        ):
            summary += token
        return summary
