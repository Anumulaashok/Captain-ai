"""Text-to-speech using piper-tts (neural, fully offline)."""
import asyncio
import io
import logging
from pathlib import Path

log = logging.getLogger(__name__)

VOICE_MODEL = "en_US-amy-medium"
VOICES_DIR = Path(__file__).parent.parent / "data" / "piper"


class TextToSpeech:
    def __init__(self):
        self._voice = None
        self._playing = False

    def _load(self):
        if self._voice is None:
            try:
                from piper.voice import PiperVoice
                model_path = VOICES_DIR / f"{VOICE_MODEL}.onnx"
                config_path = VOICES_DIR / f"{VOICE_MODEL}.onnx.json"
                if not model_path.exists():
                    log.warning(f"Piper voice model not found: {model_path}")
                    return
                self._voice = PiperVoice.load(str(model_path), config_path=str(config_path))
                log.info(f"TTS loaded: {VOICE_MODEL}")
            except ImportError:
                log.warning("piper-tts not installed")
            except Exception as e:
                log.error(f"TTS load error: {e}")

    async def speak(self, text: str) -> bytes:
        """Generate WAV audio bytes for text."""
        self._load()
        if not self._voice:
            return b""

        def _synthesize():
            buf = io.BytesIO()
            with buf:
                import wave
                with wave.open(buf, "wb") as wf:
                    audio = self._voice.synthesize(text, wf)
                return buf.getvalue()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _synthesize)

    async def speak_streaming(self, text: str):
        """Yield sentence-chunked audio for lower latency."""
        import re
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentences:
            if sentence.strip():
                audio = await self.speak(sentence.strip())
                if audio:
                    yield audio

    def stop(self):
        self._playing = False


tts = TextToSpeech()
