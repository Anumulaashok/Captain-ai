"""
Text-to-speech — tries Piper neural TTS first, falls back to macOS `say`.

Piper: high-quality offline neural voice (en_US-amy-medium)
say:   macOS built-in, always available, uses Siri neural voices
"""
import asyncio
import io
import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data" / "piper"
VOICE_MODEL = "en_US-amy-medium"
MACOS_VOICE = "Samantha"   # macOS neural voice (System Prefs → Accessibility → Spoken Content)


class TextToSpeech:
    def __init__(self):
        self._piper_voice = None
        self._piper_available: bool | None = None
        self._playing = False

    def _try_load_piper(self) -> bool:
        if self._piper_available is not None:
            return self._piper_available
        try:
            from piper.voice import PiperVoice
            model_path = DATA_DIR / f"{VOICE_MODEL}.onnx"
            config_path = DATA_DIR / f"{VOICE_MODEL}.onnx.json"
            if not model_path.exists():
                log.info("Piper model not found — using macOS say")
                self._piper_available = False
                return False
            self._piper_voice = PiperVoice.load(str(model_path), config_path=str(config_path))
            self._piper_available = True
            log.info("Piper TTS loaded (en_US-amy-medium)")
            return True
        except Exception as e:
            log.info(f"Piper unavailable ({e}) — using macOS say")
            self._piper_available = False
            return False

    # ── Public API ────────────────────────────────────────────────

    async def speak(self, text: str) -> bytes:
        """Generate WAV audio bytes. Returns b'' if using say (plays directly)."""
        if self._try_load_piper():
            return await self._piper_speak(text)
        else:
            await self._say_speak(text)
            return b""

    async def speak_and_play(self, text: str) -> None:
        """Speak text aloud — uses best available backend."""
        self._playing = True
        if self._try_load_piper():
            audio = await self._piper_speak(text)
            if audio:
                await self._play_wav(audio)
        else:
            await self._say_speak(text)
        self._playing = False

    def stop(self) -> None:
        self._playing = False
        # Kill any running say process
        subprocess.run(["pkill", "-f", "say"], capture_output=True)

    @property
    def backend(self) -> str:
        if self._piper_available:
            return "piper"
        return "macos_say"

    # ── Piper backend ──────────────────────────────────────────────

    async def _piper_speak(self, text: str) -> bytes:
        def _synth():
            buf = io.BytesIO()
            import wave
            with wave.open(buf, "wb") as wf:
                self._piper_voice.synthesize(text, wf)
            return buf.getvalue()
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _synth)

    async def _play_wav(self, wav_bytes: bytes) -> None:
        """Play WAV bytes through sounddevice."""
        def _play():
            import sounddevice as sd
            import soundfile as sf
            buf = io.BytesIO(wav_bytes)
            data, sr = sf.read(buf, dtype="float32")
            sd.play(data, sr)
            sd.wait()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _play)

    # ── macOS say backend ──────────────────────────────────────────

    async def _say_speak(self, text: str) -> None:
        """Use macOS built-in TTS (Samantha neural voice, fully offline)."""
        clean = text.replace('"', "'").replace('`', "'").replace("*", "").replace("#", "")
        cmd = ["say", "-v", MACOS_VOICE, "-r", "180", clean]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()


tts = TextToSpeech()
