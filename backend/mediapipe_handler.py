"""
MediaPipe hand tracking adapter with graceful fallback.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None

try:
    import mediapipe as mp  # type: ignore
except Exception:  # pragma: no cover
    mp = None

logger = logging.getLogger(__name__)

FINGERTIP_INDICES = [4, 8, 12, 16, 20]


@dataclass
class HandTrackResult:
    hands: list[dict[str, Any]] = field(default_factory=list)
    fps: float = 0.0
    latency_ms: float = 0.0
    resolution: tuple[int, int] = (640, 480)


class MediaPipeHandler:
    def __init__(
        self,
        *,
        min_detection_confidence: float = 0.7,
        min_tracking_confidence: float = 0.7,
        max_num_hands: int = 2,
    ) -> None:
        self._enabled = mp is not None and cv2 is not None
        self._hands = None
        self._last_ts = 0.0
        self._last_landmarks: dict[int, list[dict[str, float]]] = {}
        self._frame_counter = 0
        self._resolution = (640, 480)

        if self._enabled:
            self._hands = mp.solutions.hands.Hands(
                static_image_mode=False,
                model_complexity=0,
                max_num_hands=max_num_hands,
                min_detection_confidence=min_detection_confidence,
                min_tracking_confidence=min_tracking_confidence,
            )
            logger.info("MediaPipeHandler initialized with native mediapipe support")
        else:
            logger.warning("MediaPipe unavailable: running in tracking-disabled fallback mode")

    def process_frame(
        self,
        frame_bytes: bytes,
        *,
        target_width: int = 640,
        target_height: int = 480,
    ) -> HandTrackResult:
        start = time.perf_counter()
        now = time.perf_counter()
        delta = max(1e-6, now - self._last_ts) if self._last_ts else 0.0
        self._last_ts = now
        fps = (1.0 / delta) if delta > 0 else 0.0

        if not self._enabled or self._hands is None or cv2 is None:
            return HandTrackResult(hands=[], fps=fps, latency_ms=(time.perf_counter() - start) * 1000.0)

        arr = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return HandTrackResult(hands=[], fps=fps, latency_ms=(time.perf_counter() - start) * 1000.0)

        resized = cv2.resize(frame, (target_width, target_height))
        self._resolution = (target_width, target_height)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        result = self._hands.process(rgb)

        hands: list[dict[str, Any]] = []
        if result and result.multi_hand_landmarks:
            handedness_data = result.multi_handedness or []
            for hand_index, lm_set in enumerate(result.multi_hand_landmarks):
                label = "Unknown"
                score = 0.0
                if hand_index < len(handedness_data):
                    cls = handedness_data[hand_index].classification[0]
                    label = cls.label
                    score = float(cls.score)

                landmarks = [
                    {"x": float(pt.x), "y": float(pt.y), "z": float(pt.z)}
                    for pt in lm_set.landmark
                ]
                velocities = self._compute_fingertip_velocities(hand_index, landmarks, delta)
                hands.append(
                    {
                        "hand_index": hand_index,
                        "handedness": label,
                        "score": score,
                        "landmarks": landmarks,
                        "fingertip_velocities": velocities,
                    }
                )
                self._last_landmarks[hand_index] = landmarks

        self._frame_counter += 1
        if self._frame_counter % 60 == 0:
            # keep memory bounded in long-running sessions
            self._last_landmarks = {k: v for k, v in self._last_landmarks.items() if k < 2}

        return HandTrackResult(
            hands=hands,
            fps=fps,
            latency_ms=(time.perf_counter() - start) * 1000.0,
            resolution=self._resolution,
        )

    def _compute_fingertip_velocities(
        self,
        hand_index: int,
        landmarks: list[dict[str, float]],
        delta: float,
    ) -> dict[str, float]:
        previous = self._last_landmarks.get(hand_index)
        if not previous or delta <= 0:
            return {str(i): 0.0 for i in FINGERTIP_INDICES}

        velocities: dict[str, float] = {}
        for tip_idx in FINGERTIP_INDICES:
            if tip_idx >= len(landmarks) or tip_idx >= len(previous):
                velocities[str(tip_idx)] = 0.0
                continue
            dx = landmarks[tip_idx]["x"] - previous[tip_idx]["x"]
            dy = landmarks[tip_idx]["y"] - previous[tip_idx]["y"]
            velocities[str(tip_idx)] = float((dx * dx + dy * dy) ** 0.5 / delta)
        return velocities

    def cleanup(self) -> None:
        if self._hands is not None:
            try:
                self._hands.close()
            except Exception:
                pass
        self._hands = None

