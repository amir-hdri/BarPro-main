"""Guards on the quality-gate configuration itself.

The type-checking gate has failed silently twice in this repository's history:
once because `pyproject.toml` suppressed every error under `app/` while CI
happily reported success, and once because the CI job installed no runtime
libraries, so mypy saw `Any` in place of every third-party type. Both failures
were invisible from the outside — the job was green either way. These tests make
a regression visible in the test suite instead.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
REQUIREMENTS_TYPECHECK = REPO_ROOT / "requirements-typecheck.txt"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# Large native wheels that must stay out of the typecheck environment. numpy is
# the load-bearing one: its bundled stubs use `type` statements that mypy only
# accepts under python_version >= 3.12, and mypy is pinned to 3.11 here, so
# installing it turns the gate from "reports errors" into "crashes".
EXCLUDED_FROM_TYPECHECK = (
    "numpy",
    "pillow",
    "opencv-python-headless",
    "keras",
    "tensorflow",
    "tensorflow-cpu",
    "torch",
)


def _requirement_lines(path: Path) -> list[str]:
    lines = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        lines.append(line)
    return lines


def test_typecheck_requirements_do_not_drift_from_runtime_requirements() -> None:
    """Every typecheck pin must match requirements.txt verbatim.

    requirements.txt cannot be used as a pip constraint file (`PyJWT[crypto]`
    carries an extra and pip rejects extras in constraints), so the subset is
    duplicated by hand. This test is what keeps the duplicate honest.
    """
    runtime = set(_requirement_lines(REQUIREMENTS))
    drifted = [line for line in _requirement_lines(REQUIREMENTS_TYPECHECK) if line not in runtime]

    assert drifted == [], (
        "requirements-typecheck.txt entries not found verbatim in requirements.txt: "
        f"{drifted}. Copy the line from requirements.txt rather than pinning separately."
    )


def test_typecheck_requirements_exclude_heavy_native_wheels() -> None:
    installed = {
        line.split(">=")[0].split("==")[0].split("[")[0].strip().lower()
        for line in _requirement_lines(REQUIREMENTS_TYPECHECK)
    }
    unexpected = sorted(installed & set(EXCLUDED_FROM_TYPECHECK))

    assert unexpected == [], (
        f"{unexpected} must not be installed in the typecheck environment "
        "(see the header of requirements-typecheck.txt; numpy in particular makes mypy crash under python_version 3.11)"
    )


def _mypy_ignore_errors_modules() -> list[str]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    modules: list[str] = []
    for override in config["tool"]["mypy"].get("overrides", []):
        if not override.get("ignore_errors"):
            continue
        module = override["module"]
        modules.extend([module] if isinstance(module, str) else module)
    return modules


def test_mypy_does_not_blanket_ignore_the_backend() -> None:
    """`app.*` in an ignore_errors override makes the whole gate a no-op."""
    ignored = _mypy_ignore_errors_modules()

    assert "app.*" not in ignored, (
        "pyproject.toml suppresses every error under app/ again — the "
        "'Backend Type Checking' CI job cannot fail while this is present. "
        "List the specific packages that still have debt instead."
    )
    assert "app" not in ignored


def test_mypy_checked_packages_stay_checked() -> None:
    """Packages already at zero errors must not be added to the debt list.

    These passed with zero errors when the blanket override was removed. Adding
    any of them back would hide errors in code that is currently clean, which is
    how the blanket override grew in the first place.
    """
    ignored = set(_mypy_ignore_errors_modules())
    must_stay_checked = {
        "app.bot.*",
        "app.models.*",
        "app.monitoring.*",
        "app.realtime.*",
        "app.rpa.*",
        "app.schemas.*",
    }
    regressions = sorted(must_stay_checked & ignored)

    assert regressions == [], f"these packages were clean and must remain type-checked: {regressions}"
