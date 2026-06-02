"""Speech-to-text using faster-whisper (local, CPU-optimised)."""
import asyncio
import io
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)
WHISPER_CACHE = Path(__file__).parent.parent / "data" / "whisper"


@dataclass
class TranscriptResult:
    text: str
    language: str
    confidence: float
    duration_ms: int


class SpeechToText:
    def __init__(self):
        self._model = None

    def _load(self) -> None:
        if self._model:
            return
        from faster_whisper import WhisperModel
        log.info(f"Loading Whisper {settings.whisper_model}…")
        WHISPER_CACHE.mkdir(parents=True, exist_ok=True)
        self._model = WhisperModel(
            settings.whisper_model,
            device="cpu",
            compute_type="int8",
            download_root=str(WHISPER_CACHE),
        )
        log.info("Whisper ready")

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> TranscriptResult:
        self._load()
        t0 = time.time()

        def _run():
            import numpy as np
            import soundfile as sf
            buf = io.BytesIO(audio_bytes)
            try:
                audio, sr = sf.read(buf, dtype="float32")
            except Exception:
                # Try raw PCM fallback (16-bit, 16 kHz, mono)
                import struct
                pcm = audio_bytes
                audio = np.array(struct.unpack(f"<{len(pcm)//2}h", pcm), dtype=np.float32) / 32768.0
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            segs, info = self._model.transcribe(
                audio,
                language=language,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 600},
            )
            text = " ".join(s.text.strip() for s in segs).strip()
            return text, info.language, info.language_probability

        loop = asyncio.get_event_loop()
        text, lang, prob = await loop.run_in_executor(None, _run)
        ms = int((time.time() - t0) * 1000)
        log.debug(f"STT {ms}ms: '{text}'")
        return TranscriptResult(text=text, language=lang, confidence=round(prob, 3), duration_ms=ms)

    async def transcribe_stream(self, audio_bytes: bytes) -> TranscriptResult:
        """Alias for real-time use."""
        return await self.transcribe(audio_bytes)


stt = SpeechToText()
