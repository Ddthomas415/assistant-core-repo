"""
Wake word detection.

Listens continuously in a background thread for the trigger phrase
(default: "jarvis"). When heard, calls a callback.

Requires:
    pip install SpeechRecognition pyaudio

Uses Google Speech Recognition (free, requires internet).
For fully offline detection, swap recognizer.recognize_google with
recognizer.recognize_vosk (requires vosk + a model download).

Usage:
    from core.wake import WakeWordDetector

    detector = WakeWordDetector(on_wake=lambda: print("Wake!"))
    detector.start()   # non-blocking, runs in background thread
    ...
    detector.stop()
"""
from __future__ import annotations

import os
import threading
from typing import Callable


_WAKE_PHRASE = os.getenv("WAKE_WORD", "jarvis").lower()


class WakeWordDetector:
    """Background wake-word listener."""

    def __init__(
        self,
        on_wake: Callable[[], None],
        *,
        wake_phrase: str | None = None,
    ) -> None:
        self._on_wake    = on_wake
        self._phrase     = (wake_phrase or _WAKE_PHRASE).lower()
        self._running    = False
        self._thread: threading.Thread | None = None
        self._error: str | None = None

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def supported(self) -> bool:
        """True when required packages are available."""
        try:
            import speech_recognition  # noqa: F401
            import pyaudio             # noqa: F401
            return True
        except ImportError:
            return False

    def start(self) -> bool:
        """Start background listening. Returns False if deps are missing."""
        if not self.supported:
            self._error = "SpeechRecognition or pyaudio not installed. Run: pip install SpeechRecognition pyaudio"
            return False
        if self._running:
            return True
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        try:
            import speech_recognition as sr  # noqa: PLC0415
        except ImportError:
            self._error = "SpeechRecognition not installed."
            return

        recognizer = sr.Recognizer()
        recognizer.energy_threshold        = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold         = 0.8

        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)

        while self._running:
            try:
                with sr.Microphone() as source:
                    audio = recognizer.listen(source, timeout=5, phrase_time_limit=4)

                text = recognizer.recognize_google(audio).lower()
                if self._phrase in text:
                    self._on_wake()

            except sr.WaitTimeoutError:
                continue
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                continue
            except Exception:
                continue
