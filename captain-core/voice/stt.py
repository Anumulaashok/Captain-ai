"""Speech-to-text using faster-whisper."""
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from config import settings

log = logging.getLogger(__name__)


@dataclass
class TranscriptResult:
    text: str
    language: str
    confidence: float
    duration_ms: int


class SpeechToText:
    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            model_size = settings.whisper_model
            log.info(f"Loading Whisper model: {model_size}")
            self._model = WhisperModel(
                model_size,
                device="cpu",
                compute_type="int8",
            )
            log.info("Whisper model loaded")

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> TranscriptResult:
        import asyncio
        import time

        self._load()
        t_start = time.time()

        def _run():
            import numpy as np
            import soundfile as sf

            # Parse audio bytes to numpy array
            buf = io.BytesIO(audio_bytes)
            audio_data, sample_rate = sf.read(buf, dtype="float32")
            if audio_data.ndim > 1:
                audio_data = audio_data.mean(axis=1)

            segments, info = self._model.transcribe(
                audio_data,
                language=language,
                beam_size=5,
                best_of=5,
                temperature=0.0,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return text, info.language, info.language_probability

        loop = asyncio.get_event_loop()
        text, lang, prob = await loop.run_in_executor(None, _run)
        duration_ms = int((time.time() - t_start) * 1000)

        log.debug(f"Transcribed in {duration_ms}ms: '{text}'")
        return TranscriptResult(
            text=text,
            language=lang,
            confidence=round(prob, 3),
            duration_ms=duration_ms,
        )


stt = SpeechToText()
