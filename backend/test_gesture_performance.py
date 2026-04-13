"""
Performance-oriented checks for gesture recognition/hand tracking fallback path.
"""

from __future__ import annotations

import time
import statistics

from gesture_recognizer import GestureRecognizer
from mediapipe_handler import MediaPipeHandler


def _sample_hand():
    lm = [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(21)]
    lm[4] = {"x": 0.45, "y": 0.52, "z": 0.0}
    lm[8] = {"x": 0.46, "y": 0.52, "z": 0.0}
    return [{"handedness": "Right", "score": 0.99, "landmarks": lm}]


def test_gesture_recognition_latency_under_100ms():
    recognizer = GestureRecognizer(debounce_ms=0)
    latencies_ms = []
    for _ in range(500):
        t0 = time.perf_counter()
        recognizer.recognize(_sample_hand())
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

    assert statistics.mean(latencies_ms) < 5.0
    assert max(latencies_ms) < 100.0


def test_mediapipe_handler_fallback_does_not_crash():
    handler = MediaPipeHandler()
    # Empty bytes are invalid image data but should return graceful fallback response.
    result = handler.process_frame(b"")
    assert result.latency_ms >= 0
    assert isinstance(result.hands, list)
