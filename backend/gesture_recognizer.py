"""
Gesture recognition for MediaPipe hand landmarks.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GestureEvent:
    name: str = "none"
    confidence: float = 0.0
    timestamp: float = field(default_factory=lambda: time.time())


class GestureRecognizer:
    def __init__(self, debounce_ms: int = 100) -> None:
        self._debounce_ms = max(0, int(debounce_ms))
        self._last_emitted_name = "none"
        self._last_emitted_at = 0.0
        self._last_v_distance = None

    def recognize(self, hands: list[dict[str, Any]]) -> GestureEvent:
        if not hands:
            return GestureEvent(name="none", confidence=0.0)

        primary = self._pick_primary_hand(hands)
        landmarks = primary.get("landmarks") or []
        if len(landmarks) < 21:
            return GestureEvent(name="none", confidence=0.0)

        thumb_tip = landmarks[4]
        index_tip = landmarks[8]
        middle_tip = landmarks[12]
        ring_tip = landmarks[16]
        pinky_tip = landmarks[20]

        pinch_distance = self._distance(thumb_tip, index_tip)
        v_distance = self._distance(index_tip, middle_tip)
        fingers_extended = self._count_extended_fingers(landmarks)
        palm_forward = self._is_palm_forward(landmarks)

        name = "none"
        confidence = 0.5
        if palm_forward:
            name, confidence = "palm_forward", 0.9
        elif pinch_distance < 0.045:
            name, confidence = "pinch", 0.95
        elif fingers_extended == 5:
            name, confidence = "open_hand", 0.9
        elif fingers_extended == 0:
            name, confidence = "fist", 0.9
        elif self._is_v_sign(landmarks):
            if self._last_v_distance is not None and v_distance < self._last_v_distance * 0.78:
                name, confidence = "closing_v", 0.85
            else:
                name, confidence = "v_sign", 0.85

        self._last_v_distance = v_distance
        return self._debounced(name, confidence)

    def _pick_primary_hand(self, hands: list[dict[str, Any]]) -> dict[str, Any]:
        right = [h for h in hands if str(h.get("handedness", "")).lower() == "right"]
        candidates = right if right else hands
        return max(candidates, key=lambda h: float(h.get("score", 0.0)))

    def _count_extended_fingers(self, lm: list[dict[str, float]]) -> int:
        # thumb
        extended = 0
        if lm[4]["x"] > lm[3]["x"]:
            extended += 1
        # index/middle/ring/pinky
        for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
            if lm[tip]["y"] < lm[pip]["y"]:
                extended += 1
        return extended

    def _is_v_sign(self, lm: list[dict[str, float]]) -> bool:
        index_extended = lm[8]["y"] < lm[6]["y"]
        middle_extended = lm[12]["y"] < lm[10]["y"]
        ring_closed = lm[16]["y"] > lm[14]["y"]
        pinky_closed = lm[20]["y"] > lm[18]["y"]
        spread = self._distance(lm[8], lm[12]) > 0.07
        return index_extended and middle_extended and ring_closed and pinky_closed and spread

    def _is_palm_forward(self, lm: list[dict[str, float]]) -> bool:
        # Approximation: wrist-to-middle z relatively close and fingers open
        return abs(lm[0]["z"] - lm[9]["z"]) < 0.05 and self._count_extended_fingers(lm) >= 4

    def _distance(self, a: dict[str, float], b: dict[str, float]) -> float:
        dx = float(a["x"]) - float(b["x"])
        dy = float(a["y"]) - float(b["y"])
        return float((dx * dx + dy * dy) ** 0.5)

    def _debounced(self, name: str, confidence: float) -> GestureEvent:
        now = time.time()
        if name == self._last_emitted_name and (now - self._last_emitted_at) * 1000 < self._debounce_ms:
            return GestureEvent(name="none", confidence=0.0, timestamp=now)
        if name != "none":
            self._last_emitted_name = name
            self._last_emitted_at = now
        return GestureEvent(name=name, confidence=confidence, timestamp=now)

