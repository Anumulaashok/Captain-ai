"""Curated catalog of recommended models for 16 GB MacBooks."""
from typing import TypedDict


class ModelCatalogEntry(TypedDict):
    id: str
    name: str
    provider: str
    ollama_id: str
    family: str
    size_gb: float
    ram_required_gb: float
    quantization: str
    description: str
    recommended_for: list[str]
    quality_stars: int   # 1-5


KNOWN_MODELS: list[ModelCatalogEntry] = [
    {
        "id": "qwen2.5-7b-instruct-q4",
        "name": "Qwen 2.5 7B Instruct",
        "provider": "ollama",
        "ollama_id": "qwen2.5:7b-instruct-q4_K_M",
        "family": "qwen",
        "size_gb": 4.7,
        "ram_required_gb": 6.0,
        "quantization": "Q4_K_M",
        "description": "Best all-around model for 16 GB Macs. Fast, capable, great instruction following.",
        "recommended_for": ["chat", "tasks", "reasoning"],
        "quality_stars": 4,
    },
    {
        "id": "qwen2.5-coder-7b-q4",
        "name": "Qwen 2.5 Coder 7B",
        "provider": "ollama",
        "ollama_id": "qwen2.5-coder:7b-instruct-q4_K_M",
        "family": "qwen",
        "size_gb": 4.7,
        "ram_required_gb": 6.0,
        "quantization": "Q4_K_M",
        "description": "Specialized for code generation, debugging and review. Top coding model at this size.",
        "recommended_for": ["coding", "debugging", "code-review"],
        "quality_stars": 5,
    },
    {
        "id": "gemma2-2b-q8",
        "name": "Gemma 2 2B",
        "provider": "ollama",
        "ollama_id": "gemma2:2b-instruct-q8_0",
        "family": "gemma",
        "size_gb": 2.7,
        "ram_required_gb": 3.5,
        "quantization": "Q8_0",
        "description": "Ultra-fast lightweight model. Great for quick tasks when you need low latency.",
        "recommended_for": ["quick-chat", "summaries", "classification"],
        "quality_stars": 3,
    },
    {
        "id": "mistral-7b-v03-q5",
        "name": "Mistral 7B v0.3",
        "provider": "ollama",
        "ollama_id": "mistral:7b-instruct-v0.3-q5_K_M",
        "family": "mistral",
        "size_gb": 5.1,
        "ram_required_gb": 7.0,
        "quantization": "Q5_K_M",
        "description": "Strong reasoning and instruction following. Excellent for structured tasks.",
        "recommended_for": ["reasoning", "structured-output", "analysis"],
        "quality_stars": 4,
    },
    {
        "id": "llama3.2-3b-q8",
        "name": "Llama 3.2 3B",
        "provider": "ollama",
        "ollama_id": "llama3.2:3b-instruct-q8_0",
        "family": "llama",
        "size_gb": 3.4,
        "ram_required_gb": 4.5,
        "quantization": "Q8_0",
        "description": "Meta's compact model. Good balance of speed and quality for everyday tasks.",
        "recommended_for": ["chat", "summaries", "quick-tasks"],
        "quality_stars": 3,
    },
    {
        "id": "llava-7b-q4",
        "name": "LLaVA 7B (Multimodal)",
        "provider": "ollama",
        "ollama_id": "llava:7b-v1.6-mistral-q4_K_M",
        "family": "llava",
        "size_gb": 4.5,
        "ram_required_gb": 7.0,
        "quantization": "Q4_K_M",
        "description": "Vision + language model. Can analyze images, screenshots and documents.",
        "recommended_for": ["image-analysis", "screenshots", "documents"],
        "quality_stars": 4,
    },
    {
        "id": "phi3.5-mini-q8",
        "name": "Phi 3.5 Mini",
        "provider": "ollama",
        "ollama_id": "phi3.5:3.8b-mini-instruct-q8_0",
        "family": "phi",
        "size_gb": 4.1,
        "ram_required_gb": 5.0,
        "quantization": "Q8_0",
        "description": "Microsoft's efficient model. Punches above its weight for reasoning tasks.",
        "recommended_for": ["reasoning", "math", "coding"],
        "quality_stars": 4,
    },
    {
        "id": "deepseek-coder-6.7b-q4",
        "name": "DeepSeek Coder 6.7B",
        "provider": "ollama",
        "ollama_id": "deepseek-coder:6.7b-instruct-q4_K_M",
        "family": "deepseek",
        "size_gb": 4.0,
        "ram_required_gb": 5.5,
        "quantization": "Q4_K_M",
        "description": "Excellent code completion and generation. Strong on Python, JavaScript, Rust.",
        "recommended_for": ["coding", "autocomplete", "code-generation"],
        "quality_stars": 4,
    },
    {
        "id": "nomic-embed-text",
        "name": "Nomic Embed Text",
        "provider": "ollama",
        "ollama_id": "nomic-embed-text",
        "family": "nomic",
        "size_gb": 0.27,
        "ram_required_gb": 0.5,
        "quantization": "F16",
        "description": "Local text embedding model used for Pinecone vector search. Required for memory.",
        "recommended_for": ["embeddings", "memory", "search"],
        "quality_stars": 4,
    },
]

MODELS_BY_ID: dict[str, ModelCatalogEntry] = {m["id"]: m for m in KNOWN_MODELS}
