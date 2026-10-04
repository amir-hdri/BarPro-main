import base64

import numpy as np
import pytest

from app.automation.captcha.barname_ml_solver import (
    BarnameMlCaptchaSolver,
    MlMathCaptchaCandidate,
    _candidate_rank,
    _normalize_class_name,
    _weakest_confidence,
    barname_ml_solver,
)

SAMPLE_UTCMS_CAPTCHA_BASE64 = "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"
SAMPLE_MULTIDIGIT_CAPTCHA_BASE64 = "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"


def test_barname_ml_solver_solves_zero_sample():
    pytest.importorskip("torch", reason="requires torch for neural_net inference")
    image_bytes = base64.b64decode(SAMPLE_UTCMS_CAPTCHA_BASE64)
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    result = barname_ml_solver.solve_image(image)

    assert result is not None
    assert result.expression == "3+0"
    assert result.answer == "3"
    assert result.confidence > 0.5
    assert result.characters == ("3", "plus", "0")


def test_normalize_class_name_supports_operator_aliases_and_persian_digits():
    assert _normalize_class_name("+") == "plus"
    assert _normalize_class_name("PLUS") == "plus"
    assert _normalize_class_name("۹") == "9"
    assert _normalize_class_name("٣") == "3"


def test_barname_ml_solver_supports_digit_nine_in_expression(monkeypatch):
    solver = BarnameMlCaptchaSolver()
    solver._loaded = True
    solver._available = True

    monkeypatch.setattr(solver, "_segment", lambda _: [np.zeros((28, 28), dtype=np.uint8) for _ in range(3)])
    predictions = iter(
        [
            ("9", 0.95),
            ("plus", 0.98),
            ("0", 0.91),
        ]
    )
    monkeypatch.setattr(solver, "_predict_with_constraints", lambda _image, _allowed: next(predictions))

    result = solver.solve_image(np.zeros((64, 64), dtype=np.uint8))

    assert result is not None
    assert result.expression == "9+0"
    assert result.answer == "9"
    assert result.characters == ("9", "plus", "0")


def test_barname_ml_solver_solves_multidigit_equation():
    import cv2

    image_bytes = base64.b64decode(SAMPLE_MULTIDIGIT_CAPTCHA_BASE64)
    img = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert img is not None
    result = barname_ml_solver.solve_image(img)
    assert result is not None
    assert result.expression == "37+2"
    assert result.answer == "39"
    assert result.characters == ("3", "7", "+", "2")


def test_multidigit_short_circuit_requires_every_character_above_chance():
    """A near-chance character must not ride along on a healthy mean.

    Regression for the live defect: the UTCMS sample "3+0" was read as "8+0"
    because the multi-digit solver returned char confidences (0.033, 0.731,
    0.593) — mean 0.45, which cleared the 0.35 gate — so it short-circuited
    before the variant-segmentation solver, which reads the same image as
    "3+0" at 1.0 confidence on every character. 0.033 is below 1/11 chance.
    """
    solver = BarnameMlCaptchaSolver()
    solver._loaded = True
    solver._available = True

    weak = MlMathCaptchaCandidate(
        expression="8+0",
        answer="8",
        confidence=0.4526,
        characters=("8", "plus", "0"),
        confidences=(0.0334, 0.7312, 0.5932),
    )
    monkeypatch_target = "_solve_multidigit_or_noisy"
    assert hasattr(solver, monkeypatch_target)
    solver._solve_multidigit_or_noisy = lambda _image: weak  # type: ignore[method-assign]

    strong = iter([("3", 1.0), ("plus", 1.0), ("0", 1.0)])
    solver._segment_variants = lambda _image: [[np.zeros((28, 28), dtype=np.uint8) for _ in range(3)]]  # type: ignore[method-assign]
    solver._predict_with_constraints = lambda _image, _allowed: next(strong)  # type: ignore[method-assign]

    result = solver.solve_image(np.zeros((64, 64), dtype=np.uint8))

    assert result is not None
    # The weak-character candidate must lose despite its acceptable mean.
    assert result.expression == "3+0"
    assert result.answer == "3"
    assert min(result.confidences) >= 0.15


def test_candidate_ranking_prefers_uniform_read_over_inflated_mean():
    """Ranking is on the weakest character, then the mean."""
    inflated = MlMathCaptchaCandidate(
        expression="8+0",
        answer="8",
        confidence=0.60,
        characters=("8", "plus", "0"),
        confidences=(0.05, 0.95, 0.80),
    )
    uniform = MlMathCaptchaCandidate(
        expression="3+0",
        answer="3",
        confidence=0.55,
        characters=("3", "plus", "0"),
        confidences=(0.55, 0.55, 0.55),
    )
    assert max((inflated, uniform), key=_candidate_rank) is uniform
    assert _weakest_confidence(inflated) == 0.05
    assert _weakest_confidence(MlMathCaptchaCandidate("", "", 0.0, (), ())) == 0.0
