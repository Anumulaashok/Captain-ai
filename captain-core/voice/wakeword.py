"""OpenWakeWord listener — runs in background thread, publishes wake events."""
import asyncio
import logging
import threading
from typing import Callable

from config import settings

log = logging.getLogger(__name__)


class WakeWordDetector:
    WAKE_WORDS = ["hey_captain", "hey captain"]

    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_wake: Callable | None = None

    def set_callback(self, callback: Callable) -> None:
        self._on_wake = callback

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._running:
            return
        self._loop = loop
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()
        log.info("Wake word detector started")

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        log.info("Wake word detector stopped")

    def _listen_loop(self) -> None:
        try:
            import numpy as np
            import pyaudio
            from openwakeword.model import Model

            oww = Model(inference_framework="onnx")
            pa = pyaudio.PyAudio()
            stream = pa.open(
                rate=16000,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=1280,
            )
            log.info("Microphone open, listening for wake word...")

            while self._running:
                pcm = stream.read(1280, exception_on_overflow=False)
                audio = np.frombuffer(pcm, dtype=np.int16)
                prediction = oww.predict(audio)

                for model_name, score in prediction.items():
                    if score >= settings.wake_word_threshold:
                        log.info(f"Wake word detected! model={model_name} score={score:.3f}")
                        if self._on_wake and self._loop:
                            asyncio.run_coroutine_threadsafe(
                                self._on_wake({"score": float(score), "model": model_name}),
                                self._loop,
                            )

            stream.stop_stream()
            stream.close()
            pa.terminate()

        except ImportError:
            log.warning("openwakeword or pyaudio not installed — wake word disabled")
        except Exception as e:
            log.error(f"Wake word listener error: {e}")


wake_detector = WakeWordDetector()
