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


@router.post("/voice/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio file → text."""
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
    """Convert text to speech, return base64 WAV."""
    audio_bytes = await tts.speak(req.text)
    if not audio_bytes:
        raise HTTPException(status_code=503, detail="TTS not available")
    return {
        "audio_base64": base64.b64encode(audio_bytes).decode(),
        "mime_type": "audio/wav",
    }


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
        await voice_engine.start(mode, conv_id)

    return {"mode": mode.value}


@router.get("/voice/mode")
async def get_voice_mode():
    return {"mode": voice_engine.mode.value}
