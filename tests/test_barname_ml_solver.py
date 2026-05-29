import base64

import numpy as np

from app.automation.captcha.barname_ml_solver import (
    BarnameMlCaptchaSolver,
    _normalize_class_name,
    barname_ml_solver,
)

SAMPLE_UTCMS_CAPTCHA_BASE64 = (
    "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"
)


def test_barname_ml_solver_solves_zero_sample():
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
