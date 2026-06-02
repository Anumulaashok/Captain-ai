"""Pinecone-backed semantic memory with local Ollama embeddings."""
import logging
import uuid
from datetime import datetime

from config import settings
from memory.schemas import MemoryEntrySchema, RetrievalResult

log = logging.getLogger(__name__)


class SemanticMemory:
    EMBEDDING_MODEL = "nomic-embed-text"
    NAMESPACE_MEMORY = "memory"
    NAMESPACE_CONVERSATIONS = "conversations"
    NAMESPACE_DOCUMENTS = "documents"

    def __init__(self):
        self._pc = None
        self._index = None
        self._ollama = None

    def _get_pinecone(self):
        if self._pc is None:
            from pinecone import Pinecone
            self._pc = Pinecone(api_key=settings.pinecone_api_key)
        return self._pc

    def _get_ollama(self):
        if self._ollama is None:
            from models.ollama_client import OllamaClient
            self._ollama = OllamaClient()
        return self._ollama

    async def ensure_index(self) -> None:
        """Create Pinecone serverless index if it doesn't exist."""
        if not settings.pinecone_configured:
            log.warning("Pinecone not configured — skipping index creation")
            return
        try:
            pc = self._get_pinecone()
            existing = [idx.name for idx in pc.list_indexes()]
            if settings.pinecone_index_name not in existing:
                from pinecone import ServerlessSpec
                pc.create_index(
                    name=settings.pinecone_index_name,
                    dimension=settings.pinecone_dimension,
                    metric="cosine",
                    spec=ServerlessSpec(
                        cloud=settings.pinecone_cloud,
                        region=settings.pinecone_region,
                    ),
                )
                log.info(f"Created Pinecone index: {settings.pinecone_index_name}")
            self._index = pc.Index(settings.pinecone_index_name)
            log.info("Pinecone index ready")
        except Exception as e:
            log.error(f"Pinecone setup failed: {e}")

    def _index_client(self):
        if self._index is None:
            pc = self._get_pinecone()
            self._index = pc.Index(settings.pinecone_index_name)
        return self._index

    async def _embed(self, text: str) -> list[float] | None:
        """Generate embedding via the configured embedding model. Returns None if unavailable."""
        try:
            from models.router import model_router
            embed_model = await model_router.get_embedding_model()
            if not embed_model:
                return None
            ollama = self._get_ollama()
            return await ollama.embed(embed_model, text)
        except Exception as e:
            log.debug(f"Embedding unavailable: {e}")
            return None

    async def store(
        self,
        entry: MemoryEntrySchema,
        namespace: str = NAMESPACE_MEMORY,
    ) -> str:
        """Embed and upsert a memory entry into Pinecone."""
        if not settings.pinecone_configured:
            return entry.id

        vector = await self._embed(entry.value)
        if vector is None:
            return entry.id  # skip silently if embedding unavailable
        pinecone_id = str(uuid.uuid4())
        metadata = {
            "type": entry.type,
            "key": entry.key or "",
            "value": entry.value[:1000],  # Pinecone metadata limit
            "source": entry.source or "",
            "memory_id": entry.id,
            "created_at": entry.created_at.isoformat(),
        }
        self._index_client().upsert(
            vectors=[{"id": pinecone_id, "values": vector, "metadata": metadata}],
            namespace=namespace,
        )
        return pinecone_id

    async def search(
        self,
        query: str,
        k: int = 5,
        namespace: str = NAMESPACE_MEMORY,
        filter: dict | None = None,
    ) -> RetrievalResult:
        """Semantic search over stored memories."""
        if not settings.pinecone_configured:
            return RetrievalResult(memories=[], scores=[], query=query)

        vector = await self._embed(query)
        if vector is None:
            return RetrievalResult(memories=[], scores=[], query=query)
        results = self._index_client().query(
            vector=vector,
            top_k=k,
            include_metadata=True,
            namespace=namespace,
            filter=filter,
        )

        memories = []
        scores = []
        for match in results.get("matches", []):
            meta = match.get("metadata", {})
            memories.append(MemoryEntrySchema(
                id=meta.get("memory_id", match["id"]),
                type=meta.get("type", "fact"),
                key=meta.get("key") or None,
                value=meta.get("value", ""),
                source=meta.get("source") or None,
                pinecone_id=match["id"],
            ))
            scores.append(round(match.get("score", 0.0), 4))

        return RetrievalResult(memories=memories, scores=scores, query=query)

    async def delete(self, pinecone_id: str, namespace: str = NAMESPACE_MEMORY) -> None:
        if not settings.pinecone_configured:
            return
        self._index_client().delete(ids=[pinecone_id], namespace=namespace)

    async def store_conversation_summary(
        self, conversation_id: str, summary: str
    ) -> str:
        entry = MemoryEntrySchema(
            type="event",
            key=f"conversation:{conversation_id}",
            value=summary,
            source=conversation_id,
        )
        return await self.store(entry, namespace=self.NAMESPACE_CONVERSATIONS)

    async def store_document(self, path: str, content: str, chunk_id: str) -> str:
        entry = MemoryEntrySchema(
            id=chunk_id,
            type="document",
            key=path,
            value=content[:2000],
            source=path,
        )
        return await self.store(entry, namespace=self.NAMESPACE_DOCUMENTS)

    async def get_stats(self) -> dict:
        if not settings.pinecone_configured:
            return {"configured": False}
        try:
            stats = self._index_client().describe_index_stats()
            return {
                "configured": True,
                "index_name": settings.pinecone_index_name,
                "total_vectors": stats.get("total_vector_count", 0),
                "namespaces": dict(stats.get("namespaces", {})),
            }
        except Exception as e:
            return {"configured": True, "error": str(e)}


semantic_memory = SemanticMemory()
