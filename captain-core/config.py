from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server
    app_port: int = 8765
    app_host: str = "127.0.0.1"
    log_level: str = "INFO"
    debug: bool = False

    # Neon PostgreSQL
    database_url: str = Field(
        default="postgresql+asyncpg://localhost/captain",
        description="Neon/PostgreSQL async connection URL",
    )

    # Pinecone
    pinecone_api_key: str = ""
    pinecone_index_name: str = "captain-memory"
    pinecone_dimension: int = 1536
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"

    # LLM
    ollama_base_url: str = "http://localhost:11434"
    active_model_id: str = "qwen2.5:7b-instruct-q4_K_M"

    # Paths
    data_dir: Path = Path("./data")
    models_dir: Path = Path("./data/models")

    # Voice
    whisper_model: str = "base.en"
    voice_mode: str = "wake_word"
    wake_word_threshold: float = 0.85

    # Future cloud plugins
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""

    @property
    def pinecone_configured(self) -> bool:
        return bool(self.pinecone_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
