"""Voice Engine — coordinates wake word → STT → Orchestrator → TTS."""
import asyncio
import logging
from enum import Enum

from voice.stt import stt
from voice.tts import tts
from voice.wakeword import wake_detector

log = logging.getLogger(__name__)


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

    async def start(self, mode: VoiceMode, conversation_id: str) -> None:
        self.mode = mode
        self._active_conversation_id = conversation_id
        log.info(f"Voice engine started: mode={mode}")

        if mode == VoiceMode.WAKE_WORD:
            loop = asyncio.get_event_loop()
            wake_detector.set_callback(self._on_wake)
            wake_detector.start(loop)

        await self._publish("voice_mode_changed", {"mode": mode.value})

    async def stop(self) -> None:
        wake_detector.stop()
        self.mode = VoiceMode.DISABLED
        log.info("Voice engine stopped")

    async def push_to_talk_start(self) -> None:
        """Begin recording for push-to-talk."""
        if self._recording:
            return
        self._recording = True
        await self._publish("recording_started", {})
        asyncio.create_task(self._record_and_process())

    async def push_to_talk_stop(self) -> None:
        """Signal end of push-to-talk recording."""
        self._recording = False

    async def process_audio(self, audio_bytes: bytes) -> str:
        """Transcribe audio and process through orchestrator."""
        transcript = await stt.transcribe(audio_bytes)
        if not transcript.text.strip():
            return ""

        await self._publish("voice_transcript", {
            "text": transcript.text,
            "confidence": transcript.confidence,
        })

        # Process through orchestrator
        if self._active_conversation_id:
            from orchestrator.orchestrator import orchestrator
            response_text = ""
            async for event in orchestrator.process(
                transcript.text, self._active_conversation_id
            ):
                if event["type"] == "token":
                    response_text += event["data"].get("text", "")
                await self._publish(event["type"], event["data"])

            # TTS response
            if response_text.strip():
                await self._publish("voice_speaking", {"text": response_text})
                audio = await tts.speak(response_text)
                if audio:
                    await self._publish("voice_audio", {
                        "audio_base64": __import__("base64").b64encode(audio).decode()
                    })
                await self._publish("voice_done", {})

            return response_text
        return ""

    async def _on_wake(self, data: dict) -> None:
        await self._publish("wake_detected", data)
        # After wake word, record a short utterance
        log.info("Wake word triggered — listening for command...")
        # Record 5 seconds (simplified — production uses VAD)
        await asyncio.sleep(0.3)  # brief pause after wake word

    async def _record_and_process(self) -> None:
        try:
            import pyaudio
            import wave
            import io

            pa = pyaudio.PyAudio()
            stream = pa.open(rate=16000, channels=1, format=pyaudio.paInt16,
                             input=True, frames_per_buffer=1024)
            frames = []
            while self._recording:
                data = stream.read(1024, exception_on_overflow=False)
                frames.append(data)
            stream.stop_stream()
            stream.close()
            pa.terminate()

            # Convert to WAV bytes
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(pa.get_sample_size(pyaudio.paInt16))
                wf.setframerate(16000)
                wf.writeframes(b"".join(frames))
            await self.process_audio(buf.getvalue())
        except Exception as e:
            log.error(f"Recording error: {e}")

    async def _publish(self, event_type: str, data: dict) -> None:
        try:
            from api.websocket import event_bus
            await event_bus.publish(event_type, data)
        except Exception:
            pass


voice_engine = VoiceEngine()
