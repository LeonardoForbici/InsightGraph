from gesture_recognizer import GestureRecognizer


def _empty_hand():
    return [{"x": 0.5, "y": 0.5, "z": 0.0} for _ in range(21)]


def _wrap_hand(landmarks, handedness="Right", score=0.99):
    return [{"handedness": handedness, "score": score, "landmarks": landmarks}]


def test_recognize_pinch():
    lm = _empty_hand()
    lm[4] = {"x": 0.5, "y": 0.5, "z": 0.0}
    lm[8] = {"x": 0.52, "y": 0.5, "z": 0.0}
    recognizer = GestureRecognizer(debounce_ms=0)
    event = recognizer.recognize(_wrap_hand(lm))
    assert event.name == "pinch"


def test_recognize_open_hand():
    lm = _empty_hand()
    # thumb
    lm[3] = {"x": 0.4, "y": 0.6, "z": 0}
    lm[4] = {"x": 0.6, "y": 0.6, "z": 0}
    # index/middle/ring/pinky tips above pips
    for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
        lm[tip] = {"x": 0.5, "y": 0.2, "z": 0}
        lm[pip] = {"x": 0.5, "y": 0.5, "z": 0}
    recognizer = GestureRecognizer(debounce_ms=0)
    event = recognizer.recognize(_wrap_hand(lm))
    assert event.name in {"open_hand", "palm_forward"}


def test_recognize_v_sign_and_closing_v():
    lm = _empty_hand()
    # index/middle extended
    lm[8] = {"x": 0.4, "y": 0.2, "z": 0}
    lm[6] = {"x": 0.4, "y": 0.6, "z": 0}
    lm[12] = {"x": 0.7, "y": 0.2, "z": 0}
    lm[10] = {"x": 0.7, "y": 0.6, "z": 0}
    # ring/pinky closed
    lm[16] = {"x": 0.5, "y": 0.8, "z": 0}
    lm[14] = {"x": 0.5, "y": 0.6, "z": 0}
    lm[20] = {"x": 0.6, "y": 0.8, "z": 0}
    lm[18] = {"x": 0.6, "y": 0.6, "z": 0}

    recognizer = GestureRecognizer(debounce_ms=0)
    first = recognizer.recognize(_wrap_hand(lm))
    assert first.name in {"v_sign", "closing_v"}

    # close fingers together to trigger closing_v
    lm[12] = {"x": 0.46, "y": 0.22, "z": 0}
    second = recognizer.recognize(_wrap_hand(lm))
    assert second.name in {"closing_v", "v_sign", "none"}


def test_debounce():
    lm = _empty_hand()
    lm[4] = {"x": 0.5, "y": 0.5, "z": 0.0}
    lm[8] = {"x": 0.52, "y": 0.5, "z": 0.0}
    recognizer = GestureRecognizer(debounce_ms=500)
    first = recognizer.recognize(_wrap_hand(lm))
    second = recognizer.recognize(_wrap_hand(lm))
    assert first.name == "pinch"
    assert second.name == "none"
