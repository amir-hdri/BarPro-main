#!/usr/bin/env python3
"""Run one real, read-only UTCMS form probe through the final stage.

The probe requires an operator-supplied JSON payload and an existing active
driver.  It never fills missing values, requests an OTP/SMS, solves a final
CAPTCHA, clicks a submit control, or enables ``ALLOW_LIVE_SUBMIT``.

Example::

    python scripts/probe_waybill_final_stage.py --payload-file /secure/waybill.json --driver-id 5
"""

from __future__ import annotations

# The script adds the checkout root to sys.path before importing application
# modules so it can be invoked directly without installing the package.
# ruff: noqa: E402
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow the script to be run directly from the repository checkout.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlmodel import select

from app.auth_multitenant import decrypt_driver_password
from app.automation.browser import browser_manager
from app.automation.http_browser_bridge import ensure_utcms_http_browser_bridge
from app.automation.multitenant_payload_adapter import (
    build_enhanced_waybill_payload,
    validate_live_waybill_payload,
)
from app.automation.proxy_rotator import get_proxy_rotator
from app.automation.utcms_http_login import UtcmsHttpLogin
from app.automation.waybill_enhanced import EnhancedWaybillManager
from app.core.config import utcms_config
from app.core.database import async_session_factory
from app.models_multitenant import Driver, DriverPlate, DriverStatus
from app.services.utcms_submission_gate import utcms_submission_gate

logger = logging.getLogger("waybill_final_stage_probe")

# Read-only inventory of the real final-registration stage.  It records which
# captcha implementation UTCMS served (``#CapType`` selects one of three submit
# endpoints), the state of the OTP modal UTCMS shows *after* a save, and every
# control on the final pane -- without clicking anything.
_FINAL_STAGE_INVENTORY_JS = """
() => {
    const val = (id) => {
        const el = document.getElementById(id);
        return el ? (el.value ?? '') : null;
    };
    const describe = (el) => {
        if (!el) return null;
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return {
            tag: el.tagName.toLowerCase(),
            id: el.id || '',
            name: el.getAttribute('name') || '',
            type: el.getAttribute('type') || '',
            placeholder: el.getAttribute('placeholder') || '',
            text: (el.innerText || el.textContent || '').trim().slice(0, 60),
            cls: (el.className || '').toString().slice(0, 120),
            display: style.display,
            visible: style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0,
            disabled: !!el.disabled,
        };
    };
    const byId = (id) => describe(document.getElementById(id));

    const capType = val('CapType');
    const captchaImage = document.querySelector(
        '.dntCaptcha img, img[src*="Captcha" i], img[id*="captcha" i], #CaptchaImage'
    );

    const activePane = Array.from(document.querySelectorAll('.tab-pane'))
        .filter(p => getComputedStyle(p).display !== 'none')
        .map(p => p.id || '');

    const finalPane = document.getElementById('pills-10') || document.getElementById('pills-9');
    const finalControls = finalPane
        ? Array.from(finalPane.querySelectorAll('button, input[type=submit], input[type=button], a.btn'))
            .map(describe).filter(c => c && (c.id || c.text))
        : [];

    const otpModal = document.getElementById('GetOptCodeModal');
    return {
        captcha: {
            cap_type: capType,
            cap_type_meaning: capType === '0'
                ? 'window.cap widget -> POST /Barname/Document/UpdateRegisterNewNewOld'
                : capType === '1'
                    ? 'DNTCaptcha -> POST /Barname/Document/UpdateRegisterNewOld'
                    : 'CaptchaCode -> POST /Barname/Document/UpdateRegisterNewNew',
            cap_token_present: !!val('CapToken'),
            dnt_captcha_text_present: !!val('DNTCaptchaText'),
            dnt_captcha_token_present: !!val('DNTCaptchaToken'),
            dnt_input: byId('DNTCaptchaInputText'),
            captcha_code_input: byId('CaptchaCode'),
            dnt_refresh_button: byId('dntCaptchaRefreshButton'),
            reload_button: byId('btnReloadCaptcha'),
            image_present: !!captchaImage,
            image_src_head: captchaImage ? (captchaImage.getAttribute('src') || '').slice(0, 80) : null,
            window_cap_available: typeof window.cap !== 'undefined',
        },
        submit_controls: {
            btnRegisterFinished: byId('btnRegisterFinished'),
            btnRegisterFinishedReturn: byId('btnRegisterFinishedReturn'),
            GoFinalStep: byId('GoFinalStep'),
            btnregisterbarname: byId('btnregisterbarname'),
        },
        otp_stage: {
            modal_present: !!otpModal,
            modal_classes: otpModal ? (otpModal.className || '').toString() : null,
            modal_aria_hidden: otpModal ? otpModal.getAttribute('aria-hidden') : null,
            modal_open: !!otpModal && otpModal.classList.contains('show'),
            otp_input: byId('otp'),
            submit_otp: byId('submitOtp'),
            resend_button: byId('sendVerificationCode'),
            document_id_value: val('DocumentId'),
            timer_text: (document.getElementById('time') || {}).textContent || null,
            otp_duration: typeof otpDuration !== 'undefined' ? otpDuration : null,
        },
        tracking: {
            tracking_input: byId('TrackingCodeNumber'),
            tracking_value: val('TrackingCodeNumber'),
        },
        sms_checkbox: byId('sendsmsvalue'),
        active_panes: activePane,
        final_pane_id: finalPane ? finalPane.id : null,
        final_pane_controls: finalControls.slice(0, 25),
        open_modals: Array.from(document.querySelectorAll('.modal.show')).map(m => m.id || ''),
    };
}
"""


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, default=str), flush=True)


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"payload file could not be read: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("payload file must contain a JSON object")
    return value


async def _load_driver(driver_id: int | None, payload: dict[str, Any]) -> tuple[Driver, str, str, str]:
    vehicle = payload.get("vehicle") if isinstance(payload.get("vehicle"), dict) else {}
    requested_code = str(vehicle.get("driver_national_code") or payload.get("driver_national_code") or "").strip()

    async with async_session_factory() as session:
        if driver_id is not None:
            driver = await session.get(Driver, driver_id)
        elif requested_code:
            driver = (
                await session.exec(select(Driver).where(Driver.driver_national_code == requested_code))
            ).first()
        else:
            raise RuntimeError("driver-id or vehicle.driver_national_code is required")

        if driver is None:
            raise RuntimeError("the requested driver does not exist")
        status_value = getattr(driver.status, "value", driver.status)
        if str(status_value).lower() != DriverStatus.ACTIVE.value:
            raise RuntimeError("the requested driver is not active")
        if not driver.utcms_username or not driver.utcms_password_encrypted:
            raise RuntimeError("the requested driver has no UTCMS credentials")
        if requested_code and requested_code != str(driver.driver_national_code):
            raise RuntimeError("payload driver_national_code does not match the selected driver")

        plates = (
            await session.exec(
                select(DriverPlate)
                .where(DriverPlate.driver_id == driver.id, DriverPlate.status == "active")
                .order_by(DriverPlate.id.desc())
            )
        ).all()
        payload_plate = str(vehicle.get("plate") or "").strip()
        if not payload_plate:
            raise RuntimeError("vehicle.plate is required; the probe never invents a plate")

        from app.schemas.multitenant import _normalize_plate

        try:
            normalized_plate = _normalize_plate(payload_plate)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if not any(plate.plate_number == normalized_plate for plate in plates):
            raise RuntimeError("payload plate is not an active plate owned by the selected driver")

        password = decrypt_driver_password(driver.utcms_password_encrypted)
        return driver, driver.utcms_username, password, normalized_plate


async def run(
    payload_file: Path,
    driver_id: int | None,
    attempt_captcha: bool = False,
    captcha_artifact_dir: Path | None = None,
) -> dict[str, Any]:
    payload = _load_payload(payload_file)
    normalized = build_enhanced_waybill_payload(payload)
    driver, username, password, normalized_plate = await _load_driver(driver_id, normalized)
    normalized["vehicle"]["driver_national_code"] = driver.driver_national_code
    normalized["vehicle"]["plate"] = normalized_plate

    errors = validate_live_waybill_payload(
        normalized,
        expected_driver_national_code=driver.driver_national_code,
        expected_plate=normalized_plate,
        expected_driver_mobile=driver.phone,
    )
    if errors:
        _emit(
            {
                "status": "needs_review",
                "error_category": "payload_validation_failed",
                "errors": errors,
                "mutation_dispatched": False,
                "sms_requested": False,
            }
        )
        raise SystemExit(2)

    # The script is intentionally hard-wired to the non-mutating path.  A live
    # submission requires the separately guarded production workflow.
    utcms_config.ALLOW_LIVE_SUBMIT = False
    proxy_info = await get_proxy_rotator().get_next()
    proxy_url = proxy_info.url if proxy_info else None
    _emit(
        {
            "stage": "preflight",
            "driver_id": driver.id,
            "proxy_selected": bool(proxy_url),
            "allow_live_submit": False,
            "mutation_dispatched": False,
            "sms_requested": False,
        }
    )

    login = UtcmsHttpLogin(proxy_url=proxy_url)
    manager: EnhancedWaybillManager | None = None
    session_id: str | None = None
    try:
        login_result = await login.authenticate(username, password)
        _emit(
            {
                "stage": "login",
                "success": login_result.success,
                "status_code": login_result.status_code,
                "cookie_count": len(login_result.cookies or []),
            }
        )
        if not login_result.success:
            raise RuntimeError(login_result.error or "UTCMS login failed")

        session_id, context = await browser_manager.create_context(
            proxy_dict={"server": proxy_url} if proxy_url else None,
        )
        page = await browser_manager.new_page(context)
        bridge = await ensure_utcms_http_browser_bridge(page)
        if bridge is None:
            raise RuntimeError("UTCMS HTTP/browser bridge could not be initialized")
        await bridge.adopt_authenticated_session(login.take_authenticated_session(), login_result.cookies)

        page.on("pageerror", lambda exc: _emit({"stage": "pageerror", "message": str(exc)[:500]}))
        page.on("requestfailed", lambda req: _emit({"stage": "request_failed", "resource_type": req.resource_type}))

        await page.goto("https://barname.utcms.ir/Barname/Home", wait_until="domcontentloaded", timeout=90000)
        manager = EnhancedWaybillManager(page, context)
        result = await manager.create_waybill_with_map(
            normalized,
            dry_run=True,
            job_id="final-stage-probe",
        )
        # Read-only DOM inventory of the stage the dry run stopped on.  This
        # only evaluates getters -- it never clicks a control.
        try:
            inventory = await page.evaluate(_FINAL_STAGE_INVENTORY_JS)
        except Exception as exc:  # pragma: no cover - live-page boundary
            inventory = {"error": str(exc)[:300]}
        result["final_stage_inventory"] = inventory
        _emit({"stage": "final_stage_inventory", "inventory": inventory})

        if attempt_captcha:
            # Exercise the real solver against the live captcha image.  Filling a
            # text input mutates nothing server-side, and the solved value is
            # never emitted -- only its length and whether the fill happened.
            captcha_report: dict[str, Any] = {"attempted": True}
            try:
                await manager._handle_submit_captcha_if_present()
                captcha_report["solver_error"] = None
            except Exception as exc:
                captcha_report["solver_error"] = str(exc)[:300]
            try:
                filled_len = await page.evaluate(
                    "() => { const el = document.getElementById('DNTCaptchaInputText');"
                    " return el ? (el.value || '').trim().length : -1; }"
                )
            except Exception as exc:  # pragma: no cover - live-page boundary
                filled_len = -1
                captcha_report["readback_error"] = str(exc)[:200]
            captcha_report["input_filled"] = filled_len > 0
            captcha_report["solution_length"] = filled_len
            if captcha_artifact_dir is not None:
                # Written to disk for operator-side accuracy review only; the
                # solved value is never printed to stdout or the log.
                captcha_artifact_dir.mkdir(parents=True, exist_ok=True)
                try:
                    image_b64 = await manager._extract_captcha_image_base64(
                        "input[name='DNTCaptchaInputText']"
                    )
                    if image_b64:
                        import base64

                        (captcha_artifact_dir / "captcha.png").write_bytes(
                            base64.b64decode(image_b64.split(",")[-1])
                        )
                        captcha_report["image_saved"] = True
                    else:
                        captcha_report["image_saved"] = False
                    solved_value = await page.evaluate(
                        "() => { const el = document.getElementById('DNTCaptchaInputText');"
                        " return el ? (el.value || '').trim() : ''; }"
                    )
                    (captcha_artifact_dir / "solution.txt").write_text(
                        str(solved_value), encoding="utf-8"
                    )
                except Exception as exc:  # pragma: no cover - live-page boundary
                    captcha_report["artifact_error"] = str(exc)[:200]
            result["captcha_solver_probe"] = captcha_report
            _emit({"stage": "captcha_solver_probe", "report": captcha_report})

        gate_state = await utcms_submission_gate.get_state()
        result["probe_contract"] = {
            "final_submit_clicked": False,
            "captcha_solved": False,
            "sms_requested": False,
            "mutation_dispatched": False,
            "submission_gate_state": getattr(gate_state, "value", str(gate_state)),
        }
        _emit({"stage": "final_stage", "result": result})
        return result
    finally:
        if manager is not None:
            await manager.close()
        if session_id is not None:
            await browser_manager.close_context(session_id)
        await login.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--payload-file", required=True, type=Path)
    parser.add_argument("--driver-id", type=int)
    parser.add_argument(
        "--attempt-captcha",
        action="store_true",
        help="Run the real captcha solver against the live image (fills the input, never clicks submit).",
    )
    parser.add_argument(
        "--captcha-artifact-dir",
        type=Path,
        help="Write the live captcha image and the solver output here for accuracy review.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    try:
        asyncio.run(
            run(
                args.payload_file,
                args.driver_id,
                args.attempt_captcha,
                args.captcha_artifact_dir,
            )
        )
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:  # pragma: no cover - CLI boundary
        _emit({"status": "failed", "error": str(exc), "mutation_dispatched": False, "sms_requested": False})
        logger.debug("probe failed", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
