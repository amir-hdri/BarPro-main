# Optional CAPTCHA typing verification — 2026-10-06

Verified locally at 2026-10-06T12:48:04Z. This follow-up resolves the 22 dependency errors recorded in `otp-mypy-dependencies.log`; that earlier failure log remains historical evidence.

The five solver modules now separate optional availability handles (`ModuleType | None`) from statically typed private imports. Tensor-return casts describe the existing `nn.Module` results, and device fields explicitly allow both an uninitialized value and a Torch device. Numerical architecture, model/vocabulary filenames and normal fallback behavior are preserved. An AST comparison against HEAD confirmed every `.pth` and `.json` filename remained unchanged. No blanket type-check suppressions were added.

Fuel checkpoint loading now explicitly uses `weights_only=True`, matching the already restricted DNT, Math CRNN, Barname CNN and neural-net loaders. Evidence: `app/automation/captcha/fuel_captcha_solver.py:131`, `app/automation/captcha/dnt_captcha_solver.py:144`, `app/automation/captcha/math_crnn_solver.py:131`, `app/automation/captcha/barname_ml_solver.py:177`, `app/automation/captcha/neural_net.py:376`.

Executed results:

- `.venv/bin/mypy app/ --ignore-missing-imports`: **Success: no issues found in 216 source files**; exit 0. Log: `captcha-mypy-app-local.log`.
- `/tmp/barpro-audit-py311/bin/mypy app/ --ignore-missing-imports`: **Success: no issues found in 216 source files**; exit 0. Log: `captcha-mypy-app-ci.log`.
- `.venv/bin/pytest tests/test_captcha_no_torch.py tests/test_barname_ml_solver_no_torch.py tests/test_captcha_optional_typing.py tests/test_security_audit_gates.py tests/test_captcha_provider_factory.py tests/test_captcha_cnn_only.py tests/test_captcha_fallback.py tests/test_barname_ml_solver.py -q --tb=short --show-capture=no`: **60 passed in 1.60s**. Log: `captcha-optional-runtime-tests.log`.
- Ruff: **All checks passed**. Black `--check`: **7 files would be left unchanged**. Scoped `git diff --check`: exit 0.

Tests exercise CPU tensor inference in all five architectures, the shipped restricted DNT/Math/Fuel checkpoints, Barname image samples and simulated absence of Torch. Initial combined runs revealed test import-cache pollution: the no-Torch fixture could retain a new package binding and first-imported Torch-less modules, contaminating later inference tests. The fixture now restores both original bindings and original absence (`tests/test_captcha_no_torch.py:47`, `tests/test_captcha_no_torch.py:81`). Temporary filename changes during alias editing were caught, restored, and rechecked before the final passing run.

The Python 3.11 environment intentionally contains only type-check dependencies, so runtime tests there cannot collect without NumPy, Pillow and OpenCV. It was preserved unchanged; runtime/no-Torch behavior was tested in `.venv`, and both environments ran the full application type check.

Independent frontend review: `HistoryPage.handleSubmitOtp` reports acceptance for processing and reloads current state, matching the asynchronous service response. All six `ShippingRouteMap.bindPopup` sites use `mapPopup`, whose heading and paragraphs are assigned through `textContent` (`apps/web/src/lib/map-popup.ts:2`). Remaining `divIcon` HTML contains literals and closed-set colors. This was a source review; no additional browser execution was claimed by this subtask.
