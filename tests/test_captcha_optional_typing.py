"""Optional-import typing must preserve CPU inference and restricted model loading."""

from __future__ import annotations

import importlib
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize(
    "module_name,class_name,num_classes,input_shape,expected_shape",
    [
        ("fuel_captcha_solver", "CRNN", 7, (2, 1, 32, 300), (75, 2, 7)),
        ("dnt_captcha_solver", "CRNN", 7, (2, 1, 32, 320), (80, 2, 7)),
        ("math_crnn_solver", "MathCRNN", 13, (2, 1, 48, 160), (40, 2, 13)),
        ("barname_ml_solver", "_SimpleCNN", 11, (2, 1, 28, 28), (2, 11)),
        ("neural_net", "CaptchaCNN", None, (2, 1, 28, 28), (2, 14)),
    ],
)
def test_optional_module_aliases_preserve_tensor_inference(
    module_name, class_name, num_classes, input_shape, expected_shape
):
    torch = pytest.importorskip("torch")
    module = importlib.import_module("app.automation.captcha." + module_name)
    architecture = getattr(module, class_name)
    model = (architecture(num_classes) if num_classes is not None else architecture()).cpu().eval()
    with torch.inference_mode():
        output = model(torch.zeros(input_shape))
    assert isinstance(output, torch.Tensor)
    assert tuple(output.shape) == expected_shape
    assert bool(torch.isfinite(output).all())


def test_fuel_checkpoint_load_explicitly_restricts_unpickling(monkeypatch):
    torch = pytest.importorskip("torch")
    from app.automation.captcha.fuel_captcha_solver import PyTorchFuelCaptchaProvider

    load = Mock(wraps=torch.load)
    monkeypatch.setattr(torch, "load", load)
    solver = PyTorchFuelCaptchaProvider()
    assert solver._load_model()
    assert load.call_args.kwargs["weights_only"] is True
    with torch.inference_mode():
        output = solver._model(torch.zeros((1, 1, 32, 300)))
    assert output.shape[1:] == (1, len(solver._vocab) + 1)
    assert bool(torch.isfinite(output).all())
