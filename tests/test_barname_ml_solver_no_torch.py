"""Regression test for the torch-less graceful degradation of barname_ml_solver.

The module catches torch import failures and is supposed to degrade gracefully
(warmup() -> False, solver unavailable, fallback chain continues). Previously,
`class _SimpleCNN(nn.Module)` was defined unconditionally at import time, so a
missing torch crashed the import with AttributeError and the graceful path was
unreachable.
"""
import importlib
import sys


def test_module_imports_without_torch_and_degrades_gracefully(monkeypatch):
    # Simulate torch being unavailable.
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "torch.nn", None)

    # Force a fresh import of the module under test.
    monkeypatch.delitem(sys.modules, "app.automation.captcha.barname_ml_solver", raising=False)
    for name in [n for n in sys.modules if n.startswith("app.automation.captcha.barname_ml_solver")]:
        monkeypatch.delitem(sys.modules, name, raising=False)

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise ImportError("simulated missing torch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    module = importlib.import_module("app.automation.captcha.barname_ml_solver")

    # The CNN class must not exist without torch, and warmup must report unavailable
    # instead of raising.
    assert not hasattr(module, "_SimpleCNN")
    assert module.barname_ml_solver.warmup() is False
