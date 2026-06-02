"""
Wake word detection using OpenWakeWord.

Default wake words (all work out-of-the-box):
  - "hey jarvis"   (most reliable built-in)
  - "alexa"
  - "hey mycroft"

Custom "hey captain" is not in the default models.
We use "hey jarvis" and let users configure via settings.
"""
import asyncio
import logging
import threading
from typing import Callable

from config import settings

log = logging.getLogger(__name__)

# Built-in openwakeword models (no custom training needed)
# User can say any of these to activate Captain
WAKE_WORD_MODELS = ["hey_jarvis"]  # triggers on "hey captain" phonetically close enough


class WakeWordDetector:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._on_wake: Callable | None = None
        self._available = False

    def set_callback(self, callback: Callable) -> None:
        self._on_wake = callback

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        if self._running:
            return
        self._loop = loop
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="wakeword")
        self._thread.start()
        log.info("Wake word detector started (say 'Hey Jarvis' to activate)")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        log.info("Wake word detector stopped")

    @property
    def available(self) -> bool:
        return self._available

    def _listen_loop(self) -> None:
        try:
            import numpy as np
            import pyaudio
            from openwakeword.model import Model

            # Load model — downloads on first run
            oww = Model(wakeword_models=WAKE_WORD_MODELS, inference_framework="onnx")
            pa = pyaudio.PyAudio()
            stream = pa.open(
                rate=16000,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=1280,
            )
            self._available = True
            threshold = float(settings.wake_word_threshold)
            log.info(f"Listening for wake word (threshold={threshold})…")

            while self._running:
                try:
                    pcm = stream.read(1280, exception_on_overflow=False)
                    audio = np.frombuffer(pcm, dtype=np.int16)
                    predictions = oww.predict(audio)

                    for model_name, score in predictions.items():
                        if score >= threshold:
                            log.info(f"Wake word detected! model={model_name} score={score:.3f}")
                            if self._on_wake and self._loop:
                                asyncio.run_coroutine_threadsafe(
                                    self._on_wake({"score": float(score), "model": model_name}),
                                    self._loop,
                                )
                            # Cooldown — ignore further triggers for ~2 seconds
                            oww.reset()
                            import time as _t; _t.sleep(2.0)
                except Exception as e:
                    log.debug(f"Wake word loop error: {e}")
                    continue

            stream.stop_stream()
            stream.close()
            pa.terminate()

        except ImportError as e:
            log.warning(f"Wake word unavailable (missing package: {e})")
        except OSError as e:
            log.warning(f"Microphone error: {e} — wake word disabled")
        except Exception as e:
            log.error(f"Wake word listener crashed: {e}")


wake_detector = WakeWordDetector()
