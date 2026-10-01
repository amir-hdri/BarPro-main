"""Regression tests for torch-less graceful degradation of captcha solvers.

dnt_captcha_solver, fuel_captcha_solver, and neural_net previously crashed at
import time when torch was missing:

- dnt/fuel: ``class CRNN(nn.Module)`` evaluated with ``nn = None`` ->
  AttributeError, even though both modules had try/except torch imports and
  graceful ``torch_not_installed`` solve paths.
- neural_net: hard ``import torch`` at module top, which crashed the whole
  ``app.automation.captcha`` package import (and therefore app.main) on any
  torch-less install.

The tests simulate a missing torch and assert that every module imports,
the torch-only classes are absent, and the failure surfaces as a clear
``torch_not_installed`` error — never an import crash.
"""

import asyncio
import builtins
import importlib
import sys

import pytest

MODULES = [
    "app.automation.captcha.dnt_captcha_solver",
    "app.automation.captcha.fuel_captcha_solver",
    "app.automation.captcha.neural_net",
    "app.automation.captcha.math_crnn_solver",
]

PACKAGE = "app.automation.captcha"


def _preserve_parent_attrs(monkeypatch):
    """Preserve parent-package attribute bindings across submodule reimports.

    Reimporting ``app.automation.captcha.<sub>`` makes the import system
    overwrite the ``<sub>`` attribute on the parent package with the fresh
    module object. For submodules whose public name on the package is an
    *instance* (e.g. ``barname_ml_solver``, ``dnt_captcha_solver``), that
    silently swaps the instance for a module and breaks later tests.
    monkeypatch restores sys.modules but not these attributes, so record and
    restore them explicitly.
    """
    parent = sys.modules.get(PACKAGE)
    if parent is None:
        return
    for mod in MODULES:
        attr = mod.rsplit(".", 1)[-1]
        if hasattr(parent, attr):
            monkeypatch.setattr(parent, attr, getattr(parent, attr))


@pytest.fixture()
def no_torch(monkeypatch):
    """Simulate torch being unavailable for fresh imports of the given modules."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise ImportError("simulated missing torch")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    _preserve_parent_attrs(monkeypatch)
    # Evict torch itself and any already-imported target modules so the
    # import below re-executes module code under the fake importer.
    for name in [n for n in sys.modules if n == "torch" or n.startswith("torch.")]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    for mod in MODULES:
        for name in [n for n in sys.modules if n == mod or n.startswith(mod + ".")]:
            monkeypatch.delitem(sys.modules, name, raising=False)
    return fake_import


def _import(mod_name):
    return importlib.import_module(mod_name)


def test_dnt_solver_imports_without_torch_and_reports_unavailable(no_torch):
    module = _import("app.automation.captcha.dnt_captcha_solver")
    assert module.torch is None
    assert not hasattr(module, "CRNN")
    result = asyncio.run(module.DntCaptchaProvider().solve_text_captcha("aW1hZ2U="))
    assert result.solved is False
    assert result.error == "torch_not_installed"


def test_fuel_solver_imports_without_torch_and_reports_unavailable(no_torch):
    module = _import("app.automation.captcha.fuel_captcha_solver")
    assert module.torch is None
    assert not hasattr(module, "CRNN")
    result = asyncio.run(module.PyTorchFuelCaptchaProvider().solve_text_captcha("aW1hZ2U="))
    assert result.solved is False
    assert result.error == "torch_not_installed"


def test_neural_net_imports_without_torch_and_fails_fast(no_torch):
    module = _import("app.automation.captcha.neural_net")
    assert module.torch is None
    assert not hasattr(module, "CaptchaCNN")
    assert not hasattr(module, "MiniMLP")
    with pytest.raises(RuntimeError, match="torch_not_installed"):
        module.get_model()


def test_captcha_package_imports_without_torch(no_torch, monkeypatch):
    """The whole captcha package (imported by app.main) must survive no torch."""
    # Evict via monkeypatch (not raw del) so teardown restores the original
    # modules; otherwise a torch-less package would stay cached in sys.modules
    # and pollute torch-dependent tests later in the session.
    for name in [n for n in list(sys.modules) if n.startswith(PACKAGE)]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    pkg = importlib.import_module(PACKAGE)
    assert pkg.get_captcha_provider is not None
