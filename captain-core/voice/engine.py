"""
Voice Engine — full pipeline:
  Wake word → record → STT → Orchestrator → TTS → speak

Modes:
  DISABLED      – voice off
  WAKE_WORD     – always listening; activates on "Hey Jarvis/Captain"
  PUSH_TO_TALK  – WebSocket event starts/stops recording
  CONTINUOUS    – always transcribing (high CPU, good for demos)
"""
import asyncio
import io
import logging
import wave
from enum import Enum

from voice.stt import stt
from voice.tts import tts
from voice.wakeword import wake_detector

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHUNK = 1024
SILENCE_THRESHOLD_S = 1.5   # stop recording after 1.5s silence
MIN_SPEECH_S = 0.4           # ignore clips shorter than this


class VoiceMode(str, Enum):
    DISABLED     = "disabled"
    WAKE_WORD    = "wake_word"
    PUSH_TO_TALK = "push_to_talk"
    CONTINUOUS   = "continuous"


class VoiceEngine:
    def __init__(self):
        self.mode = VoiceMode.DISABLED
        self._active_conversation_id: str | None = None
        self._recording = False
        self._recording_frames: list[bytes] = []

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start(self, mode: VoiceMode, conversation_id: str) -> dict:
        self.mode = mode
        self._active_conversation_id = conversation_id
        log.info(f"Voice engine starting: mode={mode}")

        if mode == VoiceMode.WAKE_WORD:
            loop = asyncio.get_event_loop()
            wake_detector.set_callback(self._on_wake)
            wake_detector.start(loop)

        await self._publish("voice_mode_changed", {
            "mode": mode.value,
            "tts_backend": tts.backend,
            "wake_word": "Hey Jarvis / Hey Captain",
        })
        return {"mode": mode.value, "tts_backend": tts.backend}

    async def stop(self) -> None:
        wake_detector.stop()
        self.mode = VoiceMode.DISABLED
        log.info("Voice engine stopped")

    # ── Push-to-talk ───────────────────────────────────────────────

    async def push_to_talk_start(self) -> None:
        if self._recording:
            return
        self._recording = True
        self._recording_frames = []
        await self._publish("recording_started", {})
        asyncio.create_task(self._record_vad())

    async def push_to_talk_stop(self) -> None:
        self._recording = False

    # ── Audio processing ───────────────────────────────────────────

    async def process_audio_bytes(self, audio_bytes: bytes) -> str:
        """Main entry: transcribe audio, run through orchestrator, speak reply."""
        transcript = await stt.transcribe(audio_bytes)
        if not transcript.text.strip():
            return ""

        log.info(f"Heard: '{transcript.text}'")
        await self._publish("voice_transcript", {
            "text": transcript.text,
            "confidence": transcript.confidence,
            "duration_ms": transcript.duration_ms,
        })

        # Process through orchestrator
        response_text = await self._run_orchestrator(transcript.text)

        # Speak the response
        if response_text.strip():
            await self._publish("voice_speaking", {"text": response_text})
            await tts.speak_and_play(response_text)
            await self._publish("voice_done", {})

        return response_text

    async def _run_orchestrator(self, text: str) -> str:
        if not self._active_conversation_id:
            return ""
        from orchestrator.orchestrator import orchestrator
        response = ""
        async for event in orchestrator.process(text, self._active_conversation_id):
            if event["type"] == "token":
                response += event["data"].get("text", "")
            await self._publish(event["type"], event["data"])
        return response

    # ── Wake word callback ─────────────────────────────────────────

    async def _on_wake(self, data: dict) -> None:
        await self._publish("wake_detected", data)
        log.info("Wake word detected — recording command…")
        await asyncio.sleep(0.3)  # brief pause after wake word beep
        await self._publish("recording_started", {})
        asyncio.create_task(self._record_vad())

    # ── VAD-based recording ────────────────────────────────────────

    async def _record_vad(self) -> None:
        """Record audio until silence, then process."""
        try:
            import pyaudio
            import webrtcvad

            vad = webrtcvad.Vad(2)  # aggressiveness 0-3
            pa = pyaudio.PyAudio()
            stream = pa.open(
                rate=SAMPLE_RATE, channels=1,
                format=pyaudio.paInt16,
                input=True, frames_per_buffer=320,
            )

            frames: list[bytes] = []
            silence_frames = 0
            speech_frames = 0
            frame_duration_ms = int(320 / SAMPLE_RATE * 1000)  # 20ms
            silence_limit = int(SILENCE_THRESHOLD_S * 1000 / frame_duration_ms)

            log.debug("Recording…")
            while self._recording or speech_frames < int(MIN_SPEECH_S * 1000 / frame_duration_ms):
                frame = stream.read(320, exception_on_overflow=False)
                frames.append(frame)
                try:
                    is_speech = vad.is_speech(frame, SAMPLE_RATE)
                except Exception:
                    is_speech = True

                if is_speech:
                    speech_frames += 1
                    silence_frames = 0
                else:
                    silence_frames += 1
                    if silence_frames >= silence_limit and speech_frames > 0:
                        break

                # Safety: stop after 30 seconds
                if len(frames) > 30 * (SAMPLE_RATE // 320):
                    break

            stream.stop_stream()
            stream.close()
            pa.terminate()

            if speech_frames < int(MIN_SPEECH_S * 1000 / frame_duration_ms):
                log.debug("Too short, ignoring")
                await self._publish("recording_stopped", {"reason": "too_short"})
                return

            # Convert to WAV
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(b"".join(frames))
            audio_bytes = buf.getvalue()

            await self._publish("recording_stopped", {"frames": len(frames)})
            await self.process_audio_bytes(audio_bytes)

        except ImportError as e:
            log.error(f"Voice recording unavailable: {e}")
            await self._publish("voice_error", {"error": str(e)})
        except Exception as e:
            log.error(f"Recording error: {e}")
            await self._publish("voice_error", {"error": str(e)})

    # ── Helpers ────────────────────────────────────────────────────

    async def _publish(self, event_type: str, data: dict) -> None:
        try:
            from api.websocket import event_bus
            await event_bus.publish(event_type, data)
        except Exception:
            pass

    def get_status(self) -> dict:
        return {
            "mode": self.mode.value,
            "tts_backend": tts.backend,
            "wake_word_available": wake_detector.available,
            "wake_phrase": "Hey Jarvis (sounds like Hey Captain)",
            "conversation_id": self._active_conversation_id,
        }


voice_engine = VoiceEngine()
