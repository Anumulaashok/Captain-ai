"""MLX inference client for Apple Silicon Macs.

Falls back gracefully on Intel Macs where mlx is not available.
"""
import logging
from collections.abc import AsyncGenerator

log = logging.getLogger(__name__)

try:
    from mlx_lm import load, generate, stream_generate  # type: ignore
    MLX_AVAILABLE = True
    log.info("MLX available — Apple Silicon acceleration enabled")
except ImportError:
    MLX_AVAILABLE = False
    log.debug("MLX not available (Intel Mac or not installed)")


class MLXClient:
    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._loaded_model_path: str | None = None

    @property
    def available(self) -> bool:
        return MLX_AVAILABLE

    def load_model(self, model_path: str) -> None:
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available on this system")
        if self._loaded_model_path == model_path:
            return
        log.info(f"Loading MLX model: {model_path}")
        self._model, self._tokenizer = load(model_path)
        self._loaded_model_path = model_path
        log.info("MLX model loaded")

    def unload(self) -> None:
        self._model = None
        self._tokenizer = None
        self._loaded_model_path = None

    async def generate(
        self,
        model_path: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        if not MLX_AVAILABLE:
            raise RuntimeError("MLX not available")
        self.load_model(model_path)

        # MLX generate is synchronous; run in executor to avoid blocking event loop
        import asyncio
        loop = asyncio.get_event_loop()

        def _run():
            tokens = []
            for token in stream_generate(
                self._model,
                self._tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=temperature,
            ):
                tokens.append(token)
            return tokens

        tokens = await loop.run_in_executor(None, _run)
        for t in tokens:
            yield t
