import base64
import logging
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from voice.engine import voice_engine, VoiceMode
from voice.stt import stt
from voice.tts import tts

log = logging.getLogger(__name__)
router = APIRouter()


class VoiceModeRequest(BaseModel):
    mode: str
    conversation_id: str | None = None


class SpeakRequest(BaseModel):
    text: str


@router.get("/voice/status")
async def get_voice_status():
    return voice_engine.get_status()


@router.post("/voice/mode")
async def set_voice_mode(req: VoiceModeRequest):
    try:
        mode = VoiceMode(req.mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {req.mode}")
    if mode == VoiceMode.DISABLED:
        await voice_engine.stop()
    else:
        conv_id = req.conversation_id or "default"
        result = await voice_engine.start(mode, conv_id)
        return result
    return {"mode": mode.value}


@router.get("/voice/mode")
async def get_voice_mode():
    return {"mode": voice_engine.mode.value}


@router.post("/voice/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio → text."""
    audio_bytes = await file.read()
    result = await stt.transcribe(audio_bytes)
    return {
        "text": result.text,
        "language": result.language,
        "confidence": result.confidence,
        "duration_ms": result.duration_ms,
    }


@router.post("/voice/speak")
async def speak_text(req: SpeakRequest):
    """Text → speech. Returns base64 WAV (piper) or empty (plays via say)."""
    audio_bytes = await tts.speak(req.text)
    return {
        "audio_base64": base64.b64encode(audio_bytes).decode() if audio_bytes else "",
        "backend": tts.backend,
        "played_directly": not bool(audio_bytes),
    }


@router.post("/voice/speak-aloud")
async def speak_aloud(req: SpeakRequest):
    """Speak text aloud through speakers immediately."""
    await tts.speak_and_play(req.text)
    return {"ok": True, "backend": tts.backend}
