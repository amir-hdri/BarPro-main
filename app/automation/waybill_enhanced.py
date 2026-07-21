"""
مدیریت پیشرفته بارنامه با پشتیبانی از نقشه
"""

import asyncio
import base64
import json
import logging
import random
import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import BrowserContext, Page

from app.automation.browser import PageInteractor
from app.automation.captcha import captcha_engine, get_captcha_provider
from app.automation.location_selector import LocationSelector, RouteCalculator
from app.automation.map_controller import GeoCoordinate, MapController
from app.automation.selectors import AuthSelectors
from app.bot.core.smart_locator import SmartLocator
from app.core.config import utcms_config
from app.core.exceptions import WaybillError
from app.core.logging import monitoring_extra
from app.core.network import is_retryable_network_error
from app.core.utils import resolve_maybe_awaitable
from app.monitoring import track_captcha_attempt, track_captcha_failure, track_captcha_success
from app.monitoring.event_bridge import monitoring_bridge

logger = logging.getLogger(__name__)


class EnhancedWaybillManager:
    """مدیریت بارنامه با پشتیبانی کامل از نقشه و مکان‌یابی"""

    _captcha_digit_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    _captcha_value_pattern = re.compile(r"^-?\d+$")
    _captcha_hint_markers = (
        "captcha",
        "کپچا",
        "کد امنیتی",
        "عبارت امنیتی",
        "حاصل",
        "جمع",
        "منهای",
        "تفریق",
        "ضرب",
        "تقسیم",
        "+",
        "-",
        "*",
        "/",
        "×",
        "÷",
    )
    _plate_pattern = re.compile(r"^(\d{2})(الف|[اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی])(\d{3})ایران(\d{2})$")
    _pill_names = {
        1: "sender",
        2: "receiver",
        3: "vehicle",
        4: "cargo",
        5: "origin",
        6: "destination",
        7: "address_preview",
        8: "financial",
    }

    def __init__(self, page: Page, context: BrowserContext):
        self.page = page
        self.context = context
        self.interactor = PageInteractor(page)
        self.smart_locator = SmartLocator()
        self.map_controller = MapController(page)
        self.location_selector = LocationSelector(page)
        self.route_calculator = RouteCalculator(page)
        self._active_pill = "bootstrap"
        self._selector_inventory: dict[str, dict[str, Any]] = {}
        self._last_dialog_message: str | None = None
        self._setup_dialog_listener()

    def _setup_dialog_listener(self) -> None:
        """Register automated handler for native browser alert/confirm popups."""
        try:
            def handle_dialog(dialog):
                self._last_dialog_message = dialog.message
                logger.warning(
                    "native_browser_dialog_intercepted",
                    extra={"extra_fields": {"message": dialog.message, "type": dialog.type}},
                )
                asyncio.create_task(dialog.accept())

            self.page.on("dialog", handle_dialog)
        except Exception:
            logger.warning("failed_to_register_dialog_listener", exc_info=True)

    async def _check_and_dismiss_modal_alerts(self) -> str | None:
        """Check for visible SweetAlert, Toast, or Bootstrap modals, extract error text, and dismiss."""
        modal_selectors = [
            ".swal2-container",
            ".swal2-modal",
            ".modal.show",
            "#toast-container",
            ".bootbox",
        ]
        for sel in modal_selectors:
            try:
                if await self.page.is_visible(sel, timeout=300):
                    text = await self.page.eval_on_selector(
                        sel,
                        "el => (el.innerText || el.textContent || '').trim()"
                    )
                    logger.warning("modal_popup_detected_and_dismissing", extra={"extra_fields": {"text": text}})
                    for btn_sel in AuthSelectors.MODAL_CONFIRM_BUTTONS:
                        if await self.page.is_visible(btn_sel, timeout=200):
                            await self.page.click(btn_sel, timeout=1000)
                            break
                    return text
            except Exception:
                continue

        if self._last_dialog_message:
            msg = self._last_dialog_message
            self._last_dialog_message = None
            return msg

        return None

    @staticmethod
    def _is_valid_iranian_national_code(code: Any) -> bool:
        clean = re.sub(r"\D", "", str(code or ""))
        if len(clean) != 10 or len(set(clean)) == 1:
            return False
        check = int(clean[9])
        s = sum(int(clean[i]) * (10 - i) for i in range(9)) % 11
        return (s < 2 and check == s) or (s >= 2 and check == 11 - s)

    @staticmethod
    def _is_valid_iranian_mobile(phone: Any) -> bool:
        clean = re.sub(r"\D", "", str(phone or ""))
        if clean.startswith("98"):
            clean = "0" + clean[2:]
        return bool(re.match(r"^09\d{9}$", clean))

    def _pill_name(self, step_index: int) -> str:
        return self._pill_names.get(step_index, f"pill_{step_index}")

    def _set_active_pill(self, pill_name: str) -> None:
        self._active_pill = pill_name or "unknown"

    @staticmethod
    def _summarize_field_value(value: Any) -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""
        compact = " ".join(raw.split())
        if len(compact) <= 48:
            return compact
        return f"{compact[:45]}..."

    async def _detect_active_pane(self) -> str:
        try:
            pane_id = await self.page.evaluate(
                """() => {
                    const pane = document.querySelector('.tab-pane.active.show, .tab-pane.active');
                    return pane ? String(pane.id || '') : '';
                }"""
            )
            return str(pane_id or "")
        except Exception:
            return ""

    async def _read_button_text(self, selector: str | None, fallback_text: str = "") -> str:
        if not selector:
            return fallback_text
        try:
            value = await self.page.eval_on_selector(
                selector,
                "el => ((el.innerText || el.textContent || '').trim())",
            )
            cleaned = await self._as_clean_text(value)
            return cleaned or fallback_text
        except Exception:
            return fallback_text

    def _record_selector_inventory(
        self,
        *,
        field_label: str,
        selectors: list[str],
        status: str,
        selector_used: str | None = None,
        value: Any = None,
        pill: str | None = None,
    ) -> None:
        pill_name = pill or self._active_pill
        key = f"{pill_name}:{field_label}"
        self._selector_inventory[key] = {
            "pill": pill_name,
            "field": field_label,
            "selectors": list(selectors),
            "status": status,
            "selector_used": selector_used,
            "value_summary": self._summarize_field_value(value),
        }

    def _pill_field_summary(self, pill_name: str) -> dict[str, dict[str, str]]:
        summary: dict[str, dict[str, str]] = {}
        for item in self._selector_inventory.values():
            if item.get("pill") != pill_name:
                continue
            summary[str(item.get("field"))] = {
                "status": str(item.get("status") or ""),
                "selector": str(item.get("selector_used") or ""),
                "value": str(item.get("value_summary") or ""),
            }
        return summary

    async def _log_pill_transition(
        self,
        *,
        current_step: int,
        target_step: int,
        clicked_selector: str | None,
        button_text: str,
        transition_success: bool,
    ) -> None:
        pill_name = self._pill_name(current_step)
        active_pane = await self._detect_active_pane()
        field_values_summary = self._pill_field_summary(pill_name)
        target_pill = self._pill_name(target_step)

        payload = {
            "pill": pill_name,
            "active_pane": active_pane,
            "clicked_selector": clicked_selector,
            "button_text": button_text,
            "transition_success": transition_success,
            "target_pill": target_pill,
            "field_values_summary": field_values_summary,
        }

        logger.info(
            "waybill_pill_trace",
            extra=monitoring_extra(
                "waybill_pill_trace",
                category="waybill_flow",
                payload=payload,
                tags={"pill": pill_name, "target_pill": target_pill},
                pill=pill_name,
                active_pane=active_pane,
                clicked_selector=clicked_selector,
                button_text=button_text,
                transition_success=transition_success,
                target_pill=target_pill,
                field_values_summary=field_values_summary,
            ),
        )

        await monitoring_bridge.emit(
            "waybill_pill_trace",
            payload,
            tags={"pill": pill_name, "target_pill": target_pill},
        )

    def _log_selector_inventory_audit(self) -> None:
        audit = sorted(
            self._selector_inventory.values(), key=lambda item: (str(item.get("pill")), str(item.get("field")))
        )
        payload = {"items": audit}

        logger.info(
            "waybill_selector_inventory_audit",
            extra=monitoring_extra(
                "waybill_selector_inventory_audit",
                category="waybill_flow",
                payload=payload,
                tags={"item_count": len(audit)},
                items=audit,
                item_count=len(audit),
            ),
        )

        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(
                    monitoring_bridge.emit(
                        "waybill_selector_inventory_audit",
                        payload,
                        tags={"item_count": str(len(audit))},
                    )
                )
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

    async def _current_url(self) -> str:
        raw_url = getattr(self.page, "url", "")
        try:
            value = await resolve_maybe_awaitable(raw_url)
        except Exception:
            return ""
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)

    async def _safe_page_title(self) -> str:
        try:
            raw_title = await self.page.title()
            value = await resolve_maybe_awaitable(raw_title)
        except Exception:
            value = ""
        if value is None:
            return ""
        return (value if isinstance(value, str) else str(value)).strip()

    async def _as_clean_text(self, value: Any) -> str:
        try:
            resolved = await resolve_maybe_awaitable(value)
        except Exception:
            return ""
        if resolved is None:
            return ""
        return (resolved if isinstance(resolved, str) else str(resolved)).strip()

    @staticmethod
    def _normalize_text(value: str) -> str:
        if value is None:
            return ""
        normalized = str(value).strip().lower()
        replacements = {
            "ي": "ی",
            "ك": "ک",
            "‌": "",
            "\u200f": "",
            "\u200e": "",
            "ۀ": "ه",
            "ة": "ه",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        return "".join(normalized.split())

    @staticmethod
    def _to_english_digits(text: str) -> str:
        if text is None:
            return ""
        translation_table = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
        return str(text).translate(translation_table)

    @classmethod
    def _digits_only(cls, value: Any) -> str:
        return re.sub(r"\D", "", cls._to_english_digits(str(value or "")))

    @classmethod
    def _normalize_mobile(cls, value: Any) -> str:
        return cls._digits_only(value)

    @classmethod
    def _normalize_national_code(cls, value: Any) -> str:
        return cls._digits_only(value)

    @staticmethod
    def _split_cargo_type_and_packaging(value: Any) -> tuple[str, str | None]:
        raw = str(value or "").strip()
        if not raw:
            return "", None
        parts = [part.strip(" _-/") for part in re.split(r"[_/\\|-]+", raw) if part.strip(" _-/")]
        if not parts:
            return raw, None
        if len(parts) == 1:
            return parts[0], None
        return parts[0], parts[1]

    @classmethod
    def _parse_plate(cls, value: Any) -> dict[str, str] | None:
        compact = re.sub(r"[\s\-_/()]+", "", str(value or ""))
        compact = cls._to_english_digits(compact).replace("ايران", "ایران")
        match = cls._plate_pattern.match(compact)
        if not match:
            return None
        return {
            "first": match.group(1),
            "letter": match.group(2),
            "center": match.group(3),
            "iran": match.group(4),
        }

    @classmethod
    def _parse_free_zone_plate(cls, value: Any) -> dict[str, str] | None:
        raw = cls._to_english_digits(str(value or "")).strip()
        digit_seqs = re.findall(r"\d+", raw)
        if not digit_seqs:
            return None

        number = ""
        two_digit = ""

        if len(digit_seqs) == 1:
            seq = digit_seqs[0]
            if len(seq) == 5:
                number = seq
            elif len(seq) == 7:
                number = seq[:5]
                two_digit = seq[5:]
            elif len(seq) > 5:
                number = seq[:5]
                two_digit = seq[5:7]
            else:
                number = seq
        elif len(digit_seqs) >= 2:
            seq0, seq1 = digit_seqs[0], digit_seqs[1]
            if len(seq0) == 5:
                number = seq0
                two_digit = seq1[:2]
            elif len(seq1) == 5:
                number = seq1
                two_digit = seq0[:2]
            else:
                if len(seq0) > len(seq1):
                    number = seq0[:5]
                    two_digit = seq1[:2]
                else:
                    number = seq1[:5]
                    two_digit = seq0[:2]

        if not number:
            return None

        zones = {
            "7": ["ارس", "aras"],
            "1": ["اروند", "arvand"],
            "2": ["انزلی", "anzali"],
            "3": ["چابهار", "chabahar"],
            "4": ["قشم", "qeshm"],
            "5": ["کیش", "kish"],
            "6": ["ماکو", "maku"],
        }

        normalized = cls._normalize_text(raw)
        for zone_id, keywords in zones.items():
            for kw in keywords:
                if kw in normalized:
                    return {
                        "number": number,
                        "two_digit": two_digit,
                        "zone_id": zone_id,
                        "zone_name": keywords[0],
                    }
        return None

    @classmethod
    def _normalize_number_text(cls, value: Any, *, allow_decimal: bool = False) -> str:
        raw = cls._to_english_digits(str(value or "")).strip()
        if not raw:
            return ""
        raw = raw.replace(",", "").replace("،", "")
        if allow_decimal:
            raw = raw.replace("/", ".")
            match = re.search(r"\d+(?:\.\d+)?", raw)
        else:
            match = re.search(r"\d+", raw)
        return match.group(0) if match else ""

    async def _activate_step(self, step_index: int) -> None:
        self._set_active_pill(self._pill_name(step_index))
        tab_selector = f"#pills-{step_index}-tab"
        pane_selector = f"#pills-{step_index}"
        try:
            is_visible = await self.page.eval_on_selector(
                pane_selector,
                """el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return !el.classList.contains('hidden')
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                }""",
            )
            if is_visible:
                return
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        try:
            await self.page.click(tab_selector)
            await asyncio.sleep(0.08)
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

    async def _wait_for_step_marker(
        self,
        step_index: int,
        selectors: list[str],
        *,
        timeout_ms: int = 8000,
    ) -> bool:
        await self._activate_step(step_index)
        return await self._wait_until_any_visible(selectors, timeout_ms=timeout_ms)

    async def _select_first_non_placeholder_option(self, selector: str) -> bool:
        try:
            visible_selector = self._make_visible_selector(selector)
            option_parts = [f"{part.strip()} option" for part in visible_selector.split(",") if part.strip()]
            option_selector = ", ".join(option_parts)
            options = await self.page.eval_on_selector_all(
                option_selector,
                "els => els.map(el => ({text: (el.textContent || '').trim(), value: (el.getAttribute('value') || '').trim()}))",
            )
        except Exception:
            return False

        if not isinstance(options, list):
            return False

        for option in options:
            if not isinstance(option, dict):
                continue
            option_text = self._normalize_text(option.get("text") or "")
            option_value = str(option.get("value") or "").strip()
            if option_text in {"", "انتخاب", "انتخابکنید", "انتخابکنید..."}:
                continue
            if option_value in {"", "0"}:
                continue
            try:
                await self.page.select_option(visible_selector, value=option_value)
                return True
            except Exception:
                try:
                    await self.page.select_option(visible_selector, label=str(option.get("text") or "").strip())
                    return True
                except Exception:
                    continue
        return False

    async def _locator_current_value(self, locator) -> str:
        try:
            value = await locator.input_value()
            if value is not None:
                return str(value)
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)
        try:
            value = await locator.evaluate(
                """el => {
                    if (!el) return '';
                    if ('value' in el) return String(el.value || '');
                    return String((el.innerText || el.textContent || '').trim());
                }"""
            )
            return str(value or "")
        except Exception:
            return ""

    async def _fill_verified_text_field(
        self,
        selectors,
        value: str,
        field_label: str,
        *,
        required: bool = True,
        normalizer=None,
        prefer_type: bool = False,
    ) -> bool:
        if not value:
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="skipped",
                value=value,
            )
            return False

        expected = normalizer(value) if callable(normalizer) else str(value)

        try:
            locator = await self.smart_locator.locate(self.page, list(selectors), timeout=4000)
            if prefer_type:
                await locator.click()
                try:
                    await locator.press("ControlOrMeta+A")
                except Exception:
                    logger.warning("waybill_enhanced_silent_error", exc_info=True)
                try:
                    await locator.press("Backspace")
                except Exception:
                    logger.warning("waybill_enhanced_silent_error", exc_info=True)
                await locator.type(str(value), delay=10)
            else:
                await locator.fill(str(value))

            try:
                await locator.evaluate(
                    """el => {
                        el.dispatchEvent(new Event('keydown', { bubbles: true }));
                        el.dispatchEvent(new Event('keypress', { bubbles: true }));
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('keyup', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        if (window.jQuery) {
                            window.jQuery(el).trigger('keydown').trigger('keypress').trigger('input').trigger('keyup').trigger('change');
                        }
                    }"""
                )
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)

            await asyncio.sleep(0.01)  # Reduced from 0.05
            current = await self._locator_current_value(locator)
            normalized_current = normalizer(current) if callable(normalizer) else current
            if normalized_current == expected or self._normalize_text(str(normalized_current)) == self._normalize_text(
                str(expected)
            ):
                self._record_selector_inventory(
                    field_label=field_label,
                    selectors=list(selectors),
                    status="filled",
                    selector_used=list(selectors)[0] if selectors else None,
                    value=current,
                )
                return True
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        for selector in selectors:
            try:
                el = await self.page.query_selector(selector)
                if not el:
                    continue
                is_visible = await el.is_visible()
            except Exception:
                continue

            filler_chain = []
            if is_visible:
                if prefer_type:
                    filler_chain.append(
                        lambda selector=selector: self.page.locator(selector).first.type(
                            str(value), delay=10, timeout=1000
                        )
                    )
                filler_chain.extend(
                    (
                        lambda selector=selector: self.interactor.safe_fill(selector, str(value), timeout=1000),
                        lambda selector=selector: self._set_value_with_js(selector, str(value)),
                    )
                )
            else:
                filler_chain.append(lambda selector=selector: self._set_value_with_js(selector, str(value)))

            for filler in filler_chain:
                try:
                    result = await filler()
                    fill_success = True if prefer_type and result is None and is_visible else bool(result)
                except Exception:
                    fill_success = False
                if not fill_success:
                    continue
                await asyncio.sleep(0.05)
                try:
                    current = await self.page.eval_on_selector(
                        selector,
                        """el => {
                            if (!el) return '';
                            if ('value' in el) return String(el.value || '');
                            return String((el.innerText || el.textContent || '').trim());
                        }""",
                    )
                except Exception:
                    current = ""
                normalized_current = normalizer(current) if callable(normalizer) else str(current or "")
                if normalized_current == expected:
                    self._record_selector_inventory(
                        field_label=field_label,
                        selectors=list(selectors),
                        status="fallback-only",
                        selector_used=selector,
                        value=current,
                    )
                    return True

        if required:
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="unsupported",
                value=value,
            )
            raise WaybillError(f"پر کردن یا تایید فیلد `{field_label}` ناموفق بود")

        self._record_selector_inventory(
            field_label=field_label,
            selectors=list(selectors),
            status="unsupported",
            value=value,
        )
        logger.warning(
            "optional_fill_verification_failed",
            extra={
                "extra_fields": {
                    "field": field_label,
                    "value": str(value),
                    "selectors": list(selectors),
                }
            },
        )
        return False

    @staticmethod
    def _make_visible_selector(selector: str) -> str:
        if not selector:
            return selector
        if selector.startswith("xpath=") or "[type='hidden']" in selector or 'type="hidden"' in selector:
            return selector

        parts = []
        for part in selector.split(","):
            part_stripped = part.strip()
            if part_stripped and ":visible" not in part_stripped:
                parts.append(f"{part_stripped}:visible")
            else:
                parts.append(part_stripped)
        return ", ".join(parts)

    async def _wait_for_non_empty_value(
        self,
        selectors,
        *,
        timeout_ms: int = 6000,
    ) -> str | None:
        deadline = asyncio.get_running_loop().time() + max(0.5, timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                try:
                    visible_selector = self._make_visible_selector(selector)
                    value = await self.page.eval_on_selector(
                        visible_selector,
                        """el => {
                            if (!el) return '';
                            if ('value' in el) return String(el.value || '').trim();
                            return String((el.innerText || el.textContent || '').trim());
                        }""",
                    )
                except Exception:
                    continue
                if str(value or "").strip():
                    return str(value).strip()
            await asyncio.sleep(0.05)
        return None

    async def _is_element_visible(self, selector: str) -> bool:
        try:
            visible_selector = self._make_visible_selector(selector)
            locator = self.page.locator(visible_selector).first
            if await locator.count() == 0:
                return False
            return bool(await locator.is_visible())
        except Exception:
            return False

    async def _element_exists(self, selector: str) -> bool:
        try:
            locator = self.page.locator(selector).first
            return (await locator.count()) > 0
        except Exception:
            return False

    async def _select_option_by_fragments(
        self,
        selector: str,
        fragments: list[str],
    ) -> bool:
        cleaned_fragments = [self._normalize_text(fragment) for fragment in fragments if str(fragment or "").strip()]
        if not cleaned_fragments:
            return False
        try:
            visible_selector = self._make_visible_selector(selector)
            option_parts = [f"{part.strip()} option" for part in visible_selector.split(",") if part.strip()]
            option_selector = ", ".join(option_parts)
            options = await self.page.eval_on_selector_all(
                option_selector,
                "els => els.map(el => ({text: (el.textContent || '').trim(), value: (el.getAttribute('value') || '').trim()}))",
            )
        except Exception:
            return False

        best_value = None
        for option in options:
            option_text = self._normalize_text(str(option.get("text") or ""))
            option_value_normalized = self._normalize_text(str(option.get("value") or ""))
            option_value = str(option.get("value") or "").strip()
            if all(fragment in option_text or fragment in option_value_normalized for fragment in cleaned_fragments):
                best_value = option_value or str(option.get("text") or "").strip()
                break

        if not best_value:
            return False

        try:
            await self.page.select_option(visible_selector, value=best_value)
            return True
        except Exception:
            try:
                await self.page.select_option(visible_selector, label=best_value)
                return True
            except Exception:
                return False

    async def _log_select_options(self, selector: str, label: str) -> None:
        try:
            visible_selector = self._make_visible_selector(selector)
            option_parts = [f"{part.strip()} option" for part in visible_selector.split(",") if part.strip()]
            option_selector = ", ".join(option_parts)
            options = await self.page.eval_on_selector_all(
                option_selector,
                "els => els.map(el => ({text: (el.textContent || '').trim(), value: (el.getAttribute('value') || '').trim()}))",
            )
            option_preview = [
                {
                    "text": str((option or {}).get("text") or "")[:80],
                    "value": str((option or {}).get("value") or "")[:180],
                }
                for option in options[:10]
            ]
            logger.info(
                "select_options_snapshot",
                extra={
                    "extra_fields": {
                        "selector": selector,
                        "visible_selector": visible_selector,
                        "label": label,
                        "option_count": len(options),
                        "options": option_preview,
                    }
                },
            )
        except Exception as exc:
            logger.warning(
                "select_options_snapshot_failed",
                extra={"extra_fields": {"selector": selector, "label": label, "error": str(exc)}},
            )

    async def _set_select_value_with_js(self, selector: str, value: str) -> bool:
        try:
            updated = await self.page.eval_on_selector(
                selector,
                """(el, rawValue) => {
                    if (!el) return false;
                    const value = String(rawValue ?? '');
                    const options = Array.from(el.options || []);
                    const matched = options.find(opt => String(opt.value || '') === value || String(opt.textContent || '').trim() === value);
                    if (!matched) return false;

                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')?.set;
                    if (nativeInputValueSetter) {
                        nativeInputValueSetter.call(el, matched.value);
                    } else {
                        el.value = matched.value;
                    }
                    if (el._valueTracker) {
                        el._valueTracker.setValue(matched.value);
                    }
                    el.dispatchEvent(new Event('keydown', { bubbles: true }));
                    el.dispatchEvent(new Event('keypress', { bubbles: true }));
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('keyup', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    if (window.jQuery) {
                        window.jQuery(el).trigger('keydown').trigger('keypress').trigger('input').trigger('keyup').trigger('change');
                    }
                    return true;
                }""",
                value,
            )
            return bool(updated)
        except Exception:
            return False

    async def _js_click(self, selector: str) -> bool:
        try:
            clicked = await self.page.eval_on_selector(
                selector,
                """el => {
                    if (!el) return false;
                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    el.click();
                    return true;
                }""",
            )
            return bool(clicked)
        except Exception:
            return False

    async def _scroll_selector_into_view(self, selector: str) -> bool:
        try:
            await self.page.eval_on_selector(
                selector,
                """el => {
                    if (!el) return false;
                    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                    window.scrollBy(0, 180);
                    return true;
                }""",
            )
            await asyncio.sleep(0.05)
            return True
        except Exception:
            return False

    async def _wait_for_select_options_count(
        self,
        selector: str,
        *,
        min_count: int = 1,
        timeout_ms: int = 8000,
    ) -> int:
        deadline = asyncio.get_running_loop().time() + max(0.5, timeout_ms / 1000)
        last_count = 0
        while asyncio.get_running_loop().time() < deadline:
            try:
                visible_selector = self._make_visible_selector(selector)
                count = await self.page.eval_on_selector(
                    visible_selector,
                    """el => {
                        if (!el) return 0;
                        return Array.from(el.options || []).filter(opt => {
                            const value = String(opt.value || '').trim();
                            const text = String(opt.textContent || '').trim();
                            return value !== '' && value !== '0' && text !== '' && text !== 'انتخاب';
                        }).length;
                    }""",
                )
                last_count = int(count or 0)
            except Exception:
                last_count = 0
            if last_count >= min_count:
                return last_count
            await asyncio.sleep(0.05)
        return last_count

    async def _disable_hidden_required_fields(self, selectors: list[str]) -> int:
        disabled = 0
        for selector in selectors:
            try:
                changed = await self.page.eval_on_selector(
                    selector,
                    """el => {
                        if (!el) return 0;
                        const style = window.getComputedStyle(el);
                        const hiddenByStyle = style.display === 'none' || style.visibility === 'hidden';
                        const hiddenByTree = !el.offsetParent || !!el.closest('.d-none, .hidden, [hidden]');
                        if (!hiddenByStyle && !hiddenByTree) return 0;
                        if (el.hasAttribute('required')) {
                            el.dataset.codexRequired = 'true';
                            el.removeAttribute('required');
                        }
                        if ('disabled' in el) {
                            el.dataset.codexDisabled = 'true';
                            el.disabled = true;
                        }
                        return 1;
                    }""",
                )
                disabled += int(changed or 0)
            except Exception:
                continue
        if disabled:
            logger.info(
                "hidden_required_fields_disabled",
                extra={"extra_fields": {"selectors": selectors, "count": disabled}},
            )
        return disabled

    async def _force_tab_activation(self, step_index: int) -> bool:
        try:
            activated = await self.page.evaluate(
                r"""stepIndex => {
                    const tab = document.querySelector(`#pills-${stepIndex}-tab`);
                    const pane = document.querySelector(`#pills-${stepIndex}`);
                    if (!tab || !pane) return false;

                    // Run validation on the active form we are leaving before switching
                    if (window.jQuery) {
                        const currentTab = document.querySelector('[id^="pills-"][role="tab"].active');
                        if (currentTab) {
                            const match = currentTab.id.match(/pills-(\d+)-tab/);
                            if (match) {
                                const currentStep = parseInt(match[1]);
                                let formId = null;
                                if (currentStep === 1) formId = "frmSender";
                                else if (currentStep === 2) formId = "frmReciver";
                                else if (currentStep === 3) {
                                    const normalForm = document.getElementById("frmDriver");
                                    const isTajmi = normalForm ? normalForm.style.display === 'none' : true;
                                    formId = isTajmi ? "frmDriverTajmi" : "frmDriver";
                                }
                                else if (currentStep === 4) formId = "frmBar";
                                else if (currentStep === 5) formId = "frmmabda";
                                else if (currentStep === 6) formId = "formmagsad";
                                else if (currentStep === 7) formId = "frmkeraye";

                                if (formId) {
                                    const $form = window.jQuery("#" + formId);
                                    const fv = $form.data('formValidation');
                                    if (fv) {
                                        try {
                                            fv.validate();
                                        } catch (e) {
                                            console.error("FormValidation execution failed for " + formId, e);
                                        }
                                    }
                                }
                            }
                        }
                    }

                    document.querySelectorAll('[id^="pills-"][role="tab"]').forEach(node => {
                        node.classList.remove('active');
                        node.setAttribute('aria-selected', 'false');
                    });
                    document.querySelectorAll('.tab-pane').forEach(node => {
                        node.classList.remove('active', 'show');
                    });

                    tab.classList.add('active');
                    tab.setAttribute('aria-selected', 'true');
                    pane.classList.add('active', 'show');
                    return true;
                }""",
                step_index,
            )
            return bool(activated)
        except Exception:
            return False

    async def _force_step_transition(self, step_index: int) -> bool:
        selectors = [
            f"#GoLVL{step_index}",
            f"#pills-{step_index}-tab",
            f'button[data-to="#pills-{step_index}-tab"]',
        ]
        for selector in selectors:
            try:
                clicked = await self.interactor.safe_click(selector, wait_for_navigation=False, timeout=2000)
                if clicked:
                    await asyncio.sleep(0.08)
                    return True
            except Exception:
                continue
        for selector in selectors:
            if await self._js_click(selector):
                await asyncio.sleep(0.08)
                return True
        if await self._force_tab_activation(step_index):
            await asyncio.sleep(0.06)
            return True
        return False

    async def _try_click_next_visible_text(
        self, current_step: int, target_step: int, pane_selector: str, exact_next_text: str
    ) -> tuple[bool, str | None, str]:
        clicked_selector: str | None = None
        button_text = ""
        try:
            clicked_visible_text_button = await self.page.evaluate(
                """({ paneSelector, exactText }) => {
                    const pane = document.querySelector(paneSelector);
                    if (!pane) return false;
                    const buttons = Array.from(pane.querySelectorAll('button, a'));
                    const visible = buttons.filter(el => {
                        const text = String(el.innerText || el.textContent || '').trim();
                        const style = window.getComputedStyle(el);
                        return text === exactText
                            && style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && !el.disabled
                            && !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                    });
                    const target = visible[visible.length - 1];
                    if (!target) return false;
                    target.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                    target.click();
                    return true;
                }""",
                {"paneSelector": pane_selector, "exactText": exact_next_text},
            )
            if clicked_visible_text_button:
                await asyncio.sleep(0.1)
                clicked_selector = f"{pane_selector}::visible_text"
                button_text = exact_next_text
                if await self._wait_for_step_marker(target_step, [f"#pills-{target_step}"], timeout_ms=1800):
                    await self._log_pill_transition(
                        current_step=current_step,
                        target_step=target_step,
                        clicked_selector=clicked_selector,
                        button_text=button_text,
                        transition_success=True,
                    )
                    return True, clicked_selector, button_text
            logger.info(
                "step_next_visible_text_button_attempt",
                extra={
                    "extra_fields": {
                        "current_step": current_step,
                        "target_step": target_step,
                        "clicked": bool(clicked_visible_text_button),
                    }
                },
            )
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)
        return False, clicked_selector, button_text

    async def _try_click_next_scoped_selectors(
        self, current_step: int, target_step: int, pane_selector: str, selectors: list[str], label: str
    ) -> tuple[bool, str | None, str]:
        scoped_selectors: list[str] = []
        for selector in selectors:
            scoped_selectors.append(selector)
            if selector.startswith("#") or selector.startswith("button") or selector.startswith("a"):
                scoped_selectors.append(f"{pane_selector} {selector}")

        for selector in scoped_selectors:
            try:
                locator = self.page.locator(selector).first
                if await locator.count():
                    try:
                        await locator.scroll_into_view_if_needed(timeout=2500)
                    except Exception:
                        await self._scroll_selector_into_view(selector)
                    try:
                        await locator.click(timeout=2500)
                    except Exception:
                        try:
                            await locator.click(force=True, timeout=2500)
                        except Exception:
                            if not await self._js_click(selector):
                                continue
                    clicked_selector = selector
                    button_text = await self._read_button_text(selector, fallback_text=label)
                    await asyncio.sleep(0.08)
                    if await self._wait_for_step_marker(target_step, [f"#pills-{target_step}"], timeout_ms=1500):
                        await self._log_pill_transition(
                            current_step=current_step,
                            target_step=target_step,
                            clicked_selector=clicked_selector,
                            button_text=button_text,
                            transition_success=True,
                        )
                        return True, clicked_selector, button_text
            except Exception:
                continue
        return False, None, ""

    async def _try_click_next_fallback_selectors(
        self, current_step: int, target_step: int, label: str
    ) -> tuple[bool, str | None, str]:
        for selector in [
            f'button[data-to="#pills-{target_step}-tab"]',
            f"#GoLVL{target_step}",
        ]:
            await self._scroll_selector_into_view(selector)
            if await self._js_click(selector):
                clicked_selector = selector
                button_text = await self._read_button_text(selector, fallback_text=label)
                await asyncio.sleep(0.08)
                await self._log_pill_transition(
                    current_step=current_step,
                    target_step=target_step,
                    clicked_selector=clicked_selector,
                    button_text=button_text,
                    transition_success=True,
                )
                return True, clicked_selector, button_text
        return False, None, ""

    async def _click_step_next(
        self,
        current_step: int,
        target_step: int,
        selectors: list[str],
        label: str,
    ) -> bool:
        await self._activate_step(current_step)
        pane_selector = f"#pills-{current_step}"
        exact_next_text = "مرحله بعد"

        # 1. Try clicking button by visible text
        success, clicked_selector, button_text = await self._try_click_next_visible_text(
            current_step, target_step, pane_selector, exact_next_text
        )
        if success:
            return True

        # 2. Try scoped selectors provided
        success, clicked_selector, button_text = await self._try_click_next_scoped_selectors(
            current_step, target_step, pane_selector, selectors, label
        )
        if success:
            return True

        # 3. Try fallback generic selectors
        success, clicked_selector, button_text = await self._try_click_next_fallback_selectors(
            current_step, target_step, label
        )
        if success:
            return True

        # 4. Force step transition
        if await self._force_step_transition(target_step):
            await self._log_pill_transition(
                current_step=current_step,
                target_step=target_step,
                clicked_selector=f"#GoLVL{target_step}",
                button_text=label,
                transition_success=True,
            )
            return True

        # 5. Failed
        logger.warning(
            "step_next_click_failed",
            extra={
                "extra_fields": {
                    "current_step": current_step,
                    "target_step": target_step,
                    "label": label,
                    "selectors": selectors,
                }
            },
        )
        await self._log_pill_transition(
            current_step=current_step,
            target_step=target_step,
            clicked_selector=None,
            button_text=label,
            transition_success=False,
        )
        return False

    async def _wait_until_any_visible(self, selectors, timeout_ms: int = 5000) -> bool:
        """Wait until any of the given selectors becomes visible.

        Uses concurrent asyncio tasks for each selector so we stop as soon as
        the first one appears — no sequential polling overhead.
        """
        if not selectors:
            return False

        deadline_abs = asyncio.get_running_loop().time() + max(0.5, timeout_ms / 1000)

        async def _check_one(selector: str) -> bool:
            while asyncio.get_running_loop().time() < deadline_abs:
                if await self._is_element_visible(selector):
                    return True
                await asyncio.sleep(0.06)
            return False

        tasks = [asyncio.ensure_future(_check_one(s)) for s in selectors]
        try:
            done, pending = await asyncio.wait(
                tasks, return_when=asyncio.FIRST_COMPLETED, timeout=max(0.5, timeout_ms / 1000)
            )
            for t in pending:
                t.cancel()
            return any(t.result() for t in done if not t.cancelled() and t.exception() is None)
        except Exception:
            for t in tasks:
                t.cancel()
            return False

    async def _set_value_with_js(self, selector: str, value: str) -> bool:
        try:
            updated = await self.page.eval_on_selector(
                selector,
                """(el, rawValue) => {
                    const value = String(rawValue ?? '');
                    if (!el) return false;
                    if ('value' in el) {
                        let prototype = window.HTMLInputElement.prototype;
                        if (el instanceof window.HTMLTextAreaElement) {
                            prototype = window.HTMLTextAreaElement.prototype;
                        } else if (el instanceof window.HTMLSelectElement) {
                            prototype = window.HTMLSelectElement.prototype;
                        }
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
                        if (nativeInputValueSetter) {
                            nativeInputValueSetter.call(el, value);
                        } else {
                            el.value = value;
                        }
                        if (el._valueTracker) {
                            el._valueTracker.setValue(value);
                        }
                        el.dispatchEvent(new Event('keydown', { bubbles: true }));
                        el.dispatchEvent(new Event('keypress', { bubbles: true }));
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('keyup', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        if (window.jQuery) {
                            window.jQuery(el).trigger('keydown').trigger('keypress').trigger('input').trigger('keyup').trigger('change');
                        }
                        return true;
                    }
                    return false;
                }""",
                value,
            )
            return bool(updated)
        except Exception:
            return False

    async def _is_selector_visible(self, selector: str) -> bool:
        try:
            handle = await self.page.query_selector(selector)
            if handle is not None:
                visible = await resolve_maybe_awaitable(handle.is_visible())
                if isinstance(visible, bool):
                    return visible
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)
        try:
            locator = await self.smart_locator.locate(self.page, [selector], timeout=1200)
            return bool(await locator.is_visible())
        except Exception:
            return False

    async def _wait_for_response_match(self, matcher, timeout_ms: int = 15000):
        if not hasattr(self.page, "wait_for_response"):
            return None
        try:
            return asyncio.create_task(self.page.wait_for_response(matcher, timeout=timeout_ms))
        except Exception:
            return None

    async def _consume_json_response(self, response_task, timeout_seconds: float = 15.0) -> dict[str, Any] | None:
        if not response_task:
            return None

        try:
            response = await asyncio.wait_for(response_task, timeout=timeout_seconds)
        except Exception:
            return None

        try:
            payload = await response.json()
            if isinstance(payload, dict):
                return payload
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        try:
            raw_text = await response.text()
            payload = json.loads(raw_text)
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
        return None

    async def _wait_for_network_settle(
        self, primary_timeout_ms: int = 15000, fallback_sleep_seconds: float = 2.0
    ) -> None:
        try:
            await self.page.wait_for_load_state("networkidle", timeout=primary_timeout_ms)
            return
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=max(2000, primary_timeout_ms // 2))
            await asyncio.sleep(max(0.5, fallback_sleep_seconds))
        except Exception:
            await asyncio.sleep(max(1.0, fallback_sleep_seconds))

    @staticmethod
    def _parse_register_submit_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        success_value = payload.get("success")
        success = (
            success_value is True
            or success_value == 1
            or (isinstance(success_value, str) and success_value.strip().lower() == "true")
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        result_code = data.get("resultCode", payload.get("resultCode"))
        result_message = (
            data.get("resultMessage")
            or payload.get("message")
            or payload.get("detail")
            or payload.get("resultMessage")
            or ""
        )
        obj = data.get("obj") if isinstance(data.get("obj"), dict) else {}
        document_id = obj.get("id") or payload.get("id")
        is_otp_needed = bool(obj.get("isOtpNeeded"))

        resolved_success = success and result_code in (200, "200")
        return {
            "success": resolved_success,
            "document_id": document_id,
            "is_otp_needed": is_otp_needed,
            "message": str(result_message or ""),
            "payload": payload,
        }

    @staticmethod
    def _parse_otp_submit_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        result_code = payload.get("resultCode")
        result_message = payload.get("resultMessage") or payload.get("message") or payload.get("detail") or ""
        document_id = payload.get("obj") or payload.get("id")
        success = result_code in (200, "200")
        return {
            "success": success,
            "document_id": document_id,
            "message": str(result_message or ""),
            "payload": payload,
        }

    async def _fetch_tracking_code_by_document_id(self, document_id: Any) -> str | None:
        if not document_id:
            return None

        attempts = max(2, utcms_config.WAYBILL_MAX_RETRIES + 1)
        for attempt in range(attempts):
            try:
                raw_text = await self.page.evaluate(
                    """async (docId) => {
                        const response = await fetch(`/Barname/Document/showTrackingCode?id=${docId}`, {
                            method: 'GET',
                            credentials: 'include',
                            headers: { 'X-Requested-With': 'XMLHttpRequest' }
                        });
                        if (!response.ok) return '';
                        return await response.text();
                    }""",
                    str(document_id),
                )
            except Exception:
                raw_text = None

            text = self._to_english_digits(str(raw_text or "").strip())
            if not text or "error" in text.lower() or "not found" in text.lower() or "خطا" in text:
                await asyncio.sleep(min(2.0, 0.5 + (attempt * 0.5)))
                continue
            matches = re.findall(r"\d{6,}", text)
            if matches:
                return matches[0]

            await asyncio.sleep(min(2.0, 0.5 + (attempt * 0.5)))
        return None

    async def _click_with_fallback(
        self,
        selectors: list[str],
        label: str,
        required: bool = True,
        wait_after_seconds: float = 0.3,
    ) -> bool:
        locator = None
        try:
            locator = await self.smart_locator.locate(self.page, selectors, timeout=4500)
            await locator.click()
            await asyncio.sleep(wait_after_seconds)
            return True
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        if locator is not None:
            try:
                await locator.click(force=True)
                await asyncio.sleep(wait_after_seconds)
                return True
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)

        for selector in selectors:
            clicked = await self.interactor.safe_click(
                selector,
                wait_for_navigation=False,
                timeout=3000,
            )
            if clicked:
                await asyncio.sleep(wait_after_seconds)
                return True

        if required:
            raise WaybillError(f"کلیک روی `{label}` ناموفق بود")

        logger.warning(
            "optional_click_not_found",
            extra={"extra_fields": {"field": label, "selectors": selectors}},
        )
        return False

    async def _goto_with_retry(self, url: str, wait_until: str | None = None) -> None:
        attempts = max(1, utcms_config.PAGE_GOTO_MAX_RETRIES + 1)
        base_delay = max(0.1, utcms_config.PAGE_GOTO_RETRY_BASE_SECONDS)
        jitter = max(0.0, utcms_config.PAGE_GOTO_RETRY_JITTER_SECONDS)
        last_error: Exception | None = None
        effective_wait = wait_until or "domcontentloaded"

        for attempt in range(1, attempts + 1):
            try:
                try:
                    await self.page.goto(url, wait_until=effective_wait, timeout=utcms_config.PAGE_NAVIGATION_TIMEOUT)
                except Exception as goto_err:
                    if "timeout" in str(goto_err).lower():
                        try:
                            ready_state = await self.page.evaluate("document.readyState")
                            if ready_state in ("interactive", "complete"):
                                logger.warning(f"goto reached readyState '{ready_state}' despite timeout: {goto_err}")
                                return
                        except Exception:
                            pass
                    raise goto_err
                try:
                    await self.page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                return
            except Exception as exc:
                last_error = exc
                if attempt >= attempts or not is_retryable_network_error(exc):
                    raise
                delay = (base_delay * (2 ** (attempt - 1))) + random.uniform(0, jitter)
                await asyncio.sleep(delay)

        if last_error:
            raise last_error

    async def create_waybill_with_map(
        self,
        data: dict[str, Any],
        dry_run: bool = False,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        """
        ایجاد بارنامه با انتخاب مکان از طریق نقشه یا منوی کشویی

        Args:
            data: {
                "sender": {...},
                "receiver": {...},
                "origin": {
                    "province": "تهران",
                    "city": "تهران",
                    "district": "منطقه ۱",
                    "address": "خیابان آزادی",
                    "coordinates": {"lat": 35.6892, "lng": 51.3890}
                },
                "destination": {
                    "province": "مشهد",
                    "city": "مشهد",
                    "district": "منطقه ۲",
                    "address": "خیابان امام رضا",
                    "coordinates": {"lat": 36.2972, "lng": 59.6067}
                },
                ...
            }
        """
        try:
            # رفتن به صفحه ایجاد بارنامه
            await self._goto_with_retry(utcms_config.WAYBILL_URL, wait_until="domcontentloaded")
            try:
                await self.page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                # networkidle may not fire on heavy pages — fall back to a brief sleep
                await asyncio.sleep(1.0)
            await self._ensure_waybill_form_page()
            await self._check_account_eligibility()
            await self._wait_for_step_marker(
                1,
                ["#txtSenderFirstName", "#senderSelectType", "#btnGoLVL2"],
                timeout_ms=18000,
            )
            self._set_active_pill("sender")
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "sender"}})

            # پر کردن اطلاعات فرستنده (now handles its own next-pill transition internally)
            await self._fill_sender_info(data.get("sender", {}))

            # پر کردن اطلاعات گیرنده
            self._set_active_pill("receiver")
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "receiver"}})
            await self._fill_receiver_info(data.get("receiver", {}))

            # پر کردن اطلاعات ناوگان (handles its own next-pill transition internally)
            self._set_active_pill("vehicle")
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "vehicle"}})
            await self._fill_vehicle_info(data.get("vehicle", {}))
            await self._disable_hidden_required_fields(
                [
                    "#txtDriverSearch",
                    "#driversearchtext",
                    "#pelakFirst",
                    "#pelakCombo",
                    "#pelakCenter",
                    "#pelakIrNum",
                    "#pelakTypeCombo",
                ]
            )
            cargo_step_ready = await self._wait_for_step_marker(
                4,
                ["#txtLoadsValue", "#btnAddLoad", "#btnGoLVL5"],
                timeout_ms=15000,
            )
            if not cargo_step_ready:
                await self._js_click("#GoLVL4")
                await self._force_step_transition(4)
                await self._wait_for_step_marker(
                    4,
                    ["#txtLoadsValue", "#btnAddLoad", "#btnGoLVL5"],
                    timeout_ms=10000,
                )
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "cargo"}})
            self._set_active_pill("cargo")

            # پر کردن اطلاعات بار
            await self._fill_cargo_info(data.get("cargo", {}))

            self._set_active_pill("origin")
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "origin"}})

            # انتخاب و ثبت مبدا
            origin_result = await self._fill_origin_info(data.get("origin", {}))

            self._set_active_pill("destination")
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "destination"}})

            # انتخاب و ثبت مقصد
            dest_result = await self._fill_destination_info(data.get("destination", {}))

            self._set_active_pill("address_preview")
            preview_next_clicked = await self._click_step_next(
                7,
                8,
                [
                    '#pills-7 button[data-to="#pills-8-tab"]',
                    "#pills-7 button.btn-next",
                    '#pills-7 button:has-text("مرحله بعد")',
                ],
                "مرحله بعد (پیش‌نمایش مبدا و مقصد)",
            )
            if not preview_next_clicked:
                await self._force_step_transition(8)
            await self._wait_for_step_marker(
                8,
                ["#txtkeraye", "#loadingTime", "#btnregisterbarname"],
                timeout_ms=10000,
            )
            self._set_active_pill("financial")
            logger.info("waybill_stage_start", extra={"extra_fields": {"stage": "financial"}})

            # محاسبه مسیر در صورت وجود مختصات
            route_info = None
            if origin_result.get("coordinates") and dest_result.get("coordinates"):
                # تلاش برای استخراج مسیر از روی نقشه UI
                try:
                    await self.map_controller.wait_for_route_calculation(timeout=2000)
                    map_route_info = await self.map_controller.extract_route_info()
                    if map_route_info and map_route_info.get("distance"):
                        route_info = {
                            "distance": map_route_info.get("distance"),
                            "duration": map_route_info.get("duration"),
                            "polyline": map_route_info.get("polyline"),
                            "method": "map_extracted",
                        }
                except Exception as e:
                    logger.debug(f"استخراج مسیر از نقشه شکست خورد: {e}")

                # محاسبه دستی مسیر در صورت عدم وجود در نقشه
                if not route_info:
                    route_info = await self.route_calculator.calculate_distance(
                        GeoCoordinate(
                            latitude=origin_result["coordinates"]["lat"], longitude=origin_result["coordinates"]["lng"]
                        ),
                        GeoCoordinate(
                            latitude=dest_result["coordinates"]["lat"], longitude=dest_result["coordinates"]["lng"]
                        ),
                    )

            # پر کردن اطلاعات مالی
            await self._fill_financial_info(data.get("financial", {}))

            # مدیریت گزینه‌های حمل (two_way، end_shipping، time_limit)
            shipping_opts = data.get("shipping_options") or {}
            await self._fill_shipping_options(shipping_opts)

            financial_next_clicked = await self._click_step_next(
                8,
                9,
                [
                    "#GoPil9",
                    "button:has-text('مرحله بعد')",
                ],
                "مرحله بعد (مالی)",
            )
            if not financial_next_clicked:
                await self._force_step_transition(9)

            await self._wait_for_step_marker(
                9,
                [
                    "#btnregisterbarname",
                    "#GoFinalStep",
                    "button:has-text('مرحله نهایی')",
                    "button:has-text('ثبت بارنامه')",
                ],
                timeout_ms=18000,
            )

            # حالت ایمن: ارسال نهایی انجام نمی‌شود و فقط آمادگی ثبت ارزیابی می‌شود.
            otp_val = shipping_opts.get("otp") if isinstance(shipping_opts, dict) else None

            if dry_run:
                result = {
                    "success": True,
                    "status": "validated",
                    "validation_summary": {
                        "ready_for_submit": True,
                        "route_calculated": route_info is not None,
                        "two_way": bool(shipping_opts.get("two_way")) if isinstance(shipping_opts, dict) else False,
                        "end_shipping": shipping_opts.get("end_shipping") if isinstance(shipping_opts, dict) else None,
                        "time_limit": shipping_opts.get("time_limit") if isinstance(shipping_opts, dict) else None,
                        "otp_required": otp_val is not None,
                    },
                    "url": await self._current_url(),
                }
            else:
                # ثبت و دریافت کد رهگیری
                result = await self._submit_waybill(otp_value=otp_val, job_id=job_id)

            # افزودن اطلاعات مسیر به نتیجه
            if route_info:
                result["route"] = route_info

            result["origin_method"] = origin_result.get("method")
            result["destination_method"] = dest_result.get("method")
            if origin_result.get("map_type"):
                result["origin_map_type"] = origin_result.get("map_type")
            if dest_result.get("map_type"):
                result["destination_map_type"] = dest_result.get("map_type")

            self._log_selector_inventory_audit()
            return result

        except Exception as e:
            await self.interactor.screenshot("waybill_map_error")
            self._log_selector_inventory_audit()
            raise WaybillError(f"ایجاد بارنامه با شکست مواجه شد: {str(e)}") from e

    async def _ensure_waybill_form_page(self):
        """
        In some deployments, the configured create URL lands on a not-found shell page.
        Try to discover and open the real "حمل بارنامه" page from the side menu.
        """
        if await self._is_waybill_form_ready():
            return

        current_url = await self._current_url()
        if await self._looks_like_not_found_page():
            try:
                html = await self.page.content()
                with open("waybill_notfound_snapshot.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)

            recovery_selectors = (
                "a:has-text('ورود مجدد به سامانه')",
                "button:has-text('ورود مجدد به سامانه')",
                "a:has-text('بازگشت به خانه')",
                "button:has-text('بازگشت به خانه')",
                "a:has-text('بازگشت به صفحه اصلی')",
                "button:has-text('بازگشت به صفحه اصلی')",
            )
            for selector in recovery_selectors:
                try:
                    action = await self.smart_locator.locate(self.page, [selector], timeout=1800)
                    href = await action.get_attribute("href")
                    if href:
                        await self._goto_with_retry(urljoin(current_url, href), wait_until="domcontentloaded")
                    else:
                        await action.click()
                        await self.page.wait_for_load_state("domcontentloaded")

                    await asyncio.sleep(0.24)
                    if await self._is_waybill_form_ready():
                        return
                    current_url = await self._current_url()
                except Exception:
                    continue

        try:
            menu_links = await self.page.eval_on_selector_all(
                "a",
                "els => els.map(e => ({text:(e.innerText||'').trim(), href:(e.getAttribute('href')||'').trim()}))",
            )
            interesting = [
                item
                for item in menu_links
                if ("بارنامه" in item.get("text", "")) or ("Waybill" in item.get("href", ""))
            ]
            logger.info(
                "waybill_menu_links_discovered",
                extra={"extra_fields": {"url": current_url, "links": interesting[:20]}},
            )
            if any("درخواست دسترسی" in item.get("text", "") for item in interesting):
                raise WaybillError("حساب کاربری به ماژول صدور بارنامه دسترسی ندارد")
        except WaybillError:
            raise
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        menu_selectors = (
            "a:has-text('حمل بارنامه')",
            "a:has-text('صدور بارنامه')",
            "a[href*='Waybill' i]",
        )

        for selector in menu_selectors:
            try:
                link = await self.smart_locator.locate(self.page, [selector], timeout=1800)
                href = await link.get_attribute("href")
                if href:
                    await self._goto_with_retry(urljoin(current_url, href), wait_until="domcontentloaded")
                else:
                    await link.click()
                    await self.page.wait_for_load_state("domcontentloaded")

                await asyncio.sleep(0.3)
                if await self._is_waybill_form_ready():
                    return
            except Exception:
                continue

        for candidate_url in self._waybill_url_candidates():
            try:
                await self._goto_with_retry(candidate_url, wait_until="domcontentloaded")
                await asyncio.sleep(0.24)
                if await self._is_waybill_form_ready():
                    return
            except Exception:
                continue

        current_url = (await self._current_url()).lower()
        try:
            await self.smart_locator.locate(
                self.page,
                ["text=نامه درخواست دسترسی به سامانه صدور بارنامه شهری"],
                timeout=800,
            )
            lacks_access_banner = True
        except Exception:
            lacks_access_banner = False

        access_denied_by_text = False
        try:
            body_text = await self._as_clean_text(await self.page.text_content("body"))
            normalized_body = self._normalize_text(body_text)
            access_markers = (
                "درخواستدسترسی",
                "دسترسیبهسامانهصدوربارنامه",
                "نامهدرخواستدسترسی",
                "accessrequest",
            )
            access_denied_by_text = any(marker in normalized_body for marker in access_markers)
        except Exception:
            access_denied_by_text = False

        if "/home/infoindex" in current_url or lacks_access_banner or access_denied_by_text:
            raise WaybillError("حساب کاربری به ماژول صدور بارنامه دسترسی ندارد")

        if not await self._is_waybill_form_ready():
            raise WaybillError("فرم بارنامه پس از بازیابی در دسترس نیست")

    def _waybill_url_candidates(self) -> list[str]:
        base_url = utcms_config.BASE_URL.rstrip("/")
        candidates = [
            utcms_config.WAYBILL_URL,
            f"{base_url}/barname/Document/HagigiHogugi",
            f"{base_url}/Barname/Document/HagigiHogugi",
            f"{base_url}/Barname/Waybill/Create",
        ]
        unique: list[str] = []
        for item in candidates:
            if item and item not in unique:
                unique.append(item)
        return unique

    async def _check_account_eligibility(self) -> None:
        """
        بررسی جامع وضعیت حساب قبل از شروع فرم .
        اگر حساب مسدود، معلق، یا دارای خطای مانع است، پیش از ادامه خطا می‌دهد.
        """
        # خطاهای blocking که مانع ثبت می‌شوند
        blocking_errors = {
            "err_blocked": "حساب مسدود شده است",
            "err_suspend": "حساب معلق شده است",
            "err_incorrect_password": "رمز عبور اشتباه است",
            "err_4001_faghed_parvane": "فاقد پروانه حمل‌ونقل معتبر",
            "err_permision1": "خطای مجوز (سطح ۱)",
            "err_permision2": "خطای مجوز (سطح ۲)",
            "err_many_barname": "تعداد بارنامه‌های ثبت‌شده بیش از حد مجاز",
            "err_most_shipping": "تعداد حمل‌ها بیش از حد مجاز",
            "err_cant_shipping": "امکان ثبت حمل وجود ندارد",
            "err_barname_app": "خطای اپلیکیشن برنامه",
            "err_raod_active": "مسیر فعال دیگری وجود دارد",
            "err_arrived_target": "سفر قبلی هنوز به مقصد نرسیده",
        }
        # پیام‌های فارسی که نشان‌دهنده مشکل هستند
        blocking_persian_phrases = [
            "شما مجاز به استفاده از این بخش نمی‌باشید",
            "حساب شما مسدود شده",
            "دسترسی غیرمجاز",
            "خطا در احراز هویت",
        ]
        try:
            body_text = (await self._as_clean_text(await self.page.text_content("body"))).lower()
            for err_key, err_msg in blocking_errors.items():
                if err_key in body_text:
                    raise WaybillError(f"بررسی اولیه حساب: {err_msg}")
            for phrase in blocking_persian_phrases:
                if phrase in body_text:
                    raise WaybillError(f"بررسی اولیه حساب: {phrase}")
        except WaybillError:
            raise
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

    async def _is_waybill_form_ready(self) -> bool:
        markers = (
            'input[name="txtSenderFirstName"]',
            'input[name="SenderName"]',
            'input[name="txtReceiverFirstName"]',
            'input[name="ReceiverName"]',
            "#btnGoLVL2",
            "#GoLVL2",
        )
        for selector in markers:
            try:
                handle = await self.page.query_selector(selector)
                if handle is not None:
                    return True
            except Exception:
                continue
        for selector in markers:
            try:
                await self.smart_locator.locate(self.page, [selector], timeout=600)
                return True
            except Exception:
                continue
        return False

    async def _looks_like_not_found_page(self) -> bool:
        title = await self._safe_page_title()
        current_url = (await self._current_url()).strip().lower()

        if "یافت نشد" in title or "خطا در سامانه" in title:
            return True

        # In tests/mocks URL may not be a real HTTP URL; avoid false positives.
        if current_url and not current_url.startswith(("http://", "https://")):
            return False

        error_url_fragments = ("/error", "/exception", "/fault")
        if any(fragment in current_url for fragment in error_url_fragments):
            return True

        not_found_markers = (
            "text=یافت نشد",
            "text=صفحه مورد نظر شما یافت نشد",
            "text=درخواست مجاز نمی باشد",
            "text=خطا در سامانه",
            "text=متاسفانه در هنگام پردازش درخواست شما خطایی رخ داده است",
            "text=ورود مجدد به سامانه",
            "text=Access Denied",
            "text=فقط با آی‌پی ایران",
            "text=دسترسی شما مسدود",
            "text=آی پی شما",
            "text=IP address is blocked",
            "text=Not Found",
        )
        for marker in not_found_markers:
            try:
                await self.smart_locator.locate(self.page, [marker], timeout=500)
                return True
            except Exception:
                continue
        return False

    async def _fill_sender_info(self, sender: dict[str, str]):
        """پر کردن اطلاعات فرستنده"""
        await self._wait_for_loading_overlays_to_disappear()

        # نوع فرستنده برای حقیقی/حقوقی
        # Value 1 = حقیقی, Value 2 = حقوقی according to hagigihogugiTemplate.js
        sender_type_selectors = [
            'select[name="senderSelectType"]',
            'select[id="senderSelectType"]',
        ]

        await self._select_dropdown_with_fallback(
            sender_type_selectors,
            "1",  # Explicitly try value '1' first for real person
            "نوع فرستنده",
            required=True,
        )

        # Trigger change to reveal name fields
        try:
            await self.page.eval_on_selector(
                sender_type_selectors[0],
                "el => { el.dispatchEvent(new Event('change', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change'); } }",
            )
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        # بعد از انتخاب نوع فرستنده، ممکن است فیلدهای نام و نام خانوادگی ظاهر شوند
        await self._wait_until_any_visible(
            ["#txtSenderFirstName", "#txtSenderLastName", "#txtSenderMobile"],
            timeout_ms=4000,
        )

        sender_first = (sender.get("first_name") or "").strip()
        sender_last = (sender.get("last_name") or "").strip()
        sender_name = (sender.get("name") or "").strip()

        if not sender_first and not sender_last:
            if sender_name:
                parts = sender_name.split(maxsplit=1)
                sender_first = parts[0]
                sender_last = parts[1] if len(parts) > 1 else sender_name
            else:
                sender_first = "فرستنده"
                sender_last = "عمومی"
        elif not sender_first:
            sender_first = sender_last
        elif not sender_last:
            sender_last = sender_first

        await self._fill_verified_text_field(
            [
                'input[id="txtSenderFirstName"]',
                'input[name="txtSenderFirstName"]',
                'input[name="SenderName"]',
                'input[id="SenderName"]',
            ],
            sender_first,
            "نام فرستنده",
            required=True,
        )
        await self._fill_verified_text_field(
            [
                'input[id="txtSenderLastName"]',
                'input[name="txtSenderLastName"]',
                'input[name="SenderLastName"]',
                'input[id="SenderLastName"]',
            ],
            sender_last,
            "نام خانوادگی فرستنده",
            required=True,
        )

        # National code / company code (optional)
        sender_national_code = (sender.get("national_code") or sender.get("national_id") or "").strip()
        if sender_national_code:
            await self._fill_verified_text_field(
                [
                    'input[name="txtSenderNationalCode"]',
                    'input[id="txtSenderNationalCode"]',
                    'input[name="SenderNationalCode"]',
                    'input[id="SenderNationalCode"]',
                ],
                self._normalize_national_code(sender_national_code),
                "کد ملی فرستنده",
                required=False,
                normalizer=self._normalize_national_code,
            )

        sender_phone = sender.get("phone", "")
        await self._fill_verified_text_field(
            [
                'input[name="txtSenderMobile"]',
                'input[id="txtSenderMobile"]',
            ],
            self._normalize_mobile(sender_phone),
            "تلفن فرستنده",
            required=bool(sender_phone),
            normalizer=self._normalize_mobile,
            prefer_type=True,
        )

        # Click Next and check for validation errors
        sender_next = await self._click_step_next(
            1,
            2,
            ["#btnGoLVL2", "#GoLVL2", 'button[data-to="#pills-2-tab"]'],
            "مرحله بعد (فرستنده)",
        )
        if not sender_next:
            modal_err = await self._check_and_dismiss_modal_alerts()
            if modal_err:
                raise WaybillError(f"خطای فرم فرستنده: {modal_err}")
            await self._force_step_transition(2)

        # Verify we actually moved to pill 2; if not, extract and raise the form error
        pill2_ready = await self._wait_for_step_marker(
            2,
            ["#txtReceiverFirstName", "#receiverSelectType", "#btnGoLVL3"],
            timeout_ms=5000,
        )
        if not pill2_ready:
            form_errors = await self._extract_form_errors() or await self._check_and_dismiss_modal_alerts()
            error_msg = form_errors or "اعتبارسنجی فرم فرستنده ناموفق بود"
            logger.error("sender_form_validation_blocked", extra={"extra_fields": {"errors": error_msg}})
            raise WaybillError(f"گذر از مرحله فرستنده ناموفق بود: {error_msg}")

    async def _fill_receiver_info(self, receiver: dict[str, str]):
        """پر کردن اطلاعات گیرنده"""
        await self._wait_for_loading_overlays_to_disappear()

        receiver_type_selectors = [
            'select[name="receiverSelectType"]',
            'select[id="receiverSelectType"]',
        ]
        await self._select_dropdown_with_fallback(
            receiver_type_selectors,
            "1",  # Value 1 = حقیقی
            "نوع گیرنده",
            required=True,
        )
        # Trigger change
        try:
            await self.page.eval_on_selector(
                receiver_type_selectors[0],
                "el => { el.dispatchEvent(new Event('change', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change'); } }",
            )
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        await self._wait_until_any_visible(
            ["#txtReceiverFirstName", "#txtReceiverLastName", "#txtReceiverMobile"],
            timeout_ms=4000,
        )

        receiver_first = (receiver.get("first_name") or "").strip()
        receiver_last = (receiver.get("last_name") or "").strip()
        receiver_name = (receiver.get("name") or "").strip()

        if not receiver_first and not receiver_last:
            if receiver_name:
                parts = receiver_name.split(maxsplit=1)
                receiver_first = parts[0]
                receiver_last = parts[1] if len(parts) > 1 else receiver_name
            else:
                receiver_first = "گیرنده"
                receiver_last = "عمومی"
        elif not receiver_first:
            receiver_first = receiver_last
        elif not receiver_last:
            receiver_last = receiver_first

        await self._fill_verified_text_field(
            [
                'input[id="txtReceiverFirstName"]',
                'input[name="txtReceiverFirstName"]',
                'input[name="ReceiverName"]',
                'input[id="ReceiverName"]',
            ],
            receiver_first,
            "نام گیرنده",
            required=True,
        )
        await self._fill_verified_text_field(
            [
                'input[id="txtReceiverLastName"]',
                'input[name="txtReceiverLastName"]',
                'input[name="ReceiverLastName"]',
                'input[id="ReceiverLastName"]',
            ],
            receiver_last,
            "نام خانوادگی گیرنده",
            required=True,
        )

        # National code (optional)
        receiver_national_code = (receiver.get("national_code") or receiver.get("national_id") or "").strip()
        if receiver_national_code:
            await self._fill_verified_text_field(
                [
                    'input[name="txtReceiverNationalCode"]',
                    'input[id="txtReceiverNationalCode"]',
                    'input[name="ReceiverNationalCode"]',
                    'input[id="ReceiverNationalCode"]',
                ],
                self._normalize_national_code(receiver_national_code),
                "کد ملی گیرنده",
                required=False,
                normalizer=self._normalize_national_code,
            )

        receiver_phone = receiver.get("phone", "")
        await self._fill_verified_text_field(
            [
                'input[name="txtReceiverMobile"]',
                'input[id="txtReceiverMobile"]',
            ],
            self._normalize_mobile(receiver_phone),
            "تلفن گیرنده",
            required=bool(receiver_phone),
            normalizer=self._normalize_mobile,
            prefer_type=True,
        )

        receiver_next = await self._click_step_next(
            2,
            3,
            ["#btnGoLVL3", "#GoLVL3", 'button[data-to="#pills-3-tab"]'],
            "مرحله بعد (گیرنده)",
        )
        if not receiver_next:
            await self._force_step_transition(3)

        # Verify we actually moved to pill 3
        pill3_ready = await self._wait_for_step_marker(
            3,
            ["#txtDriverSearch", "#PelakComboTajmi", "#DriverListTajmi", "#btnGoLVL4"],
            timeout_ms=5000,
        )
        if not pill3_ready:
            form_errors = await self._extract_form_errors()
            error_msg = form_errors or "اعتبارسنجی فرم گیرنده ناموفق بود"
            logger.error("receiver_form_validation_blocked", extra={"extra_fields": {"errors": error_msg}})
            raise WaybillError(f"گذر از مرحله گیرنده ناموفق بود: {error_msg}")

    async def _fill_cargo_info(self, cargo: dict[str, Any]):
        """پر کردن اطلاعات کالا"""
        # Validate input data first
        if not cargo:
            raise WaybillError("اطلاعات کالا ارائه نشده است")
        if not cargo.get("type"):
            raise WaybillError("تایپ کالا (cargo.type) الزامی است")
        if not isinstance(cargo.get("type"), str) or len(cargo["type"].strip()) < 2:
            raise WaybillError(f"تایپ کالا معتبر نیست: {cargo.get('type')}")

        await self._wait_for_loading_overlays_to_disappear()
        await self._wait_for_step_marker(4, ["#txtLoadsValue", "#btnAddLoad"], timeout_ms=8000)

        # Check if the "Add Cargo" button/modal trigger is present and visible
        if await self._is_element_visible("#btnAddLoad"):
            logger.info("cargo_modal_trigger_visible_clicking")
            await self._click_with_fallback(["#btnAddLoad"], "دکمه افزودن کالا")
            try:
                # Wait for the modal or one of the form inputs inside it to be visible
                await self.page.wait_for_selector("#txtLoadName", state="visible", timeout=3000)
            except Exception:
                logger.warning("cargo_input_not_visible_after_modal_click_attempting_anyway")

        cargo_name, packaging_hint = self._split_cargo_type_and_packaging(cargo.get("type"))

        # انتخاب نوع کالا
        if cargo.get("type"):
            cargo_query = cargo_name or str(cargo["type"])
            await self._fill_verified_text_field(
                [
                    "#txtLoadName",
                    'input[id="txtLoadName"]',
                    'input[name="txtLoadName"]',
                ],
                cargo_query,
                "نام کالا",
                required=True,
                prefer_type=True,
            )

            # Wait for autocomplete dropdown to appear (UI layer option selection)
            dropdown_selected = False
            try:
                await self.page.wait_for_selector(".ui-autocomplete:visible", timeout=3000)
                items = await self.page.locator(".ui-autocomplete:visible .ui-menu-item").all()
                if items:
                    await items[0].click()
                    dropdown_selected = True
                    logger.info("cargo_autocomplete_selected_via_ui")
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)

            # If UI selection didn't work/happen, fall back to API-based lookup and manual JS set
            if not dropdown_selected:
                logger.info("cargo_autocomplete_ui_failed_trying_api_lookup")
                try:
                    search_results = await self.page.evaluate(
                        """async (term) => {
                            return new Promise((resolve) => {
                                if (!window.jQuery) {
                                    resolve([]);
                                    return;
                                }
                                window.jQuery.ajax({
                                    url: "/Barname/Document/KalaSearch",
                                    data: { txtkala: term },
                                    success: function(doc) {
                                        try {
                                            const parsed = typeof doc === 'string' ? JSON.parse(doc) : doc;
                                            resolve(parsed || []);
                                        } catch(e) {
                                            resolve([]);
                                        }
                                    },
                                    error: function() {
                                        resolve([]);
                                    }
                                });
                            });
                        }""",
                        cargo_query,
                    )
                except Exception as ex:
                    logger.warning(f"cargo_api_lookup_failed: {ex}")
                    search_results = []

                selected_id = None
                selected_name = cargo_query

                if search_results and isinstance(search_results, list):
                    best_match = None
                    normalized_query = self._normalize_text(cargo_query)
                    for res in search_results:
                        if not isinstance(res, dict):
                            continue
                        label = str(res.get("label") or res.get("value") or "").strip()
                        normalized_label = self._normalize_text(label)
                        if normalized_query in normalized_label or normalized_label in normalized_query:
                            best_match = res
                            break
                    if not best_match and search_results:
                        best_match = search_results[0]

                    if best_match and isinstance(best_match, dict):
                        selected_id = str(best_match.get("id") or "")
                        selected_name = str(best_match.get("label") or best_match.get("value") or cargo_query)

                if not selected_id:
                    selected_id = cargo_query

                try:
                    await self.page.eval_on_selector(
                        "#selecteditme",
                        """(el, val) => {
                            if (!el) return;
                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                            if (nativeSetter) {
                                nativeSetter.call(el, val);
                            } else {
                                el.value = val;
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            if (window.jQuery) {
                                window.jQuery(el).trigger('input').trigger('change');
                            }
                        }""",
                        selected_id,
                    )

                    await self.page.eval_on_selector(
                        "#txtLoadName",
                        """(el, name) => {
                            if (!el) return;
                            const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                            if (nativeSetter) {
                                nativeSetter.call(el, name);
                            } else {
                                el.value = name;
                            }
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                            if (window.jQuery) {
                                window.jQuery(el).trigger('input').trigger('change');
                            }
                        }""",
                        selected_name,
                    )
                    logger.info(
                        "cargo_fields_set_via_js", extra={"extra_fields": {"id": selected_id, "name": selected_name}}
                    )
                except Exception as ex:
                    logger.error(f"failed_setting_cargo_fields_via_js: {ex}")

        # Wait for dynamic box type options to load
        try:
            await self._wait_for_select_options_count("#ddBoxType", min_count=1, timeout_ms=6000)
        except Exception as ex:
            logger.warning(f"failed_waiting_for_ddBoxType_options: {ex}")

        packaging_value = packaging_hint or cargo.get("packaging") or cargo.get("description")
        selected_packaging = False
        if packaging_value:
            selected_packaging = await self._select_dropdown_with_fallback(
                [
                    "#ddBoxType",
                    'select[name="ddBoxType"]',
                    'select[id="ddBoxType"]',
                ],
                str(packaging_value),
                "نوع بسته بندی",
                required=False,
            )

        if not selected_packaging:
            # Fall back to first non-placeholder option if specific option was not found or not provided
            selected_packaging = await self._select_first_non_placeholder_option("#ddBoxType")
            if selected_packaging:
                logger.info("cargo_packaging_selected_first_non_placeholder")
            else:
                logger.warning("cargo_packaging_selection_failed_no_options")

        weight_val = cargo.get("weight")
        await self._fill_verified_text_field(
            [
                "#txtWeight",
                'input[name="txtWeight"]',
                'input[id="txtWeight"]',
                'input[name="CargoWeight"]',
                'input[id="CargoWeight"]',
            ],
            self._normalize_number_text(weight_val, allow_decimal=True),
            "وزن کالا",
            required=bool(weight_val),
        )
        count_val = cargo.get("count")
        await self._fill_verified_text_field(
            [
                "#txtBoxNum",
                'input[name="txtBoxNum"]',
                'input[id="txtBoxNum"]',
                'input[name="CargoCount"]',
                'input[id="CargoCount"]',
            ],
            self._normalize_number_text(count_val or "1"),
            "تعداد کالا",
            required=bool(count_val),
        )
        desc_val = cargo.get("description")
        await self._fill_verified_text_field(
            [
                "#txtLoadDetail",
                'textarea[name="txtLoadDetail"]',
                'textarea[id="txtLoadDetail"]',
                'textarea[name="CargoDescription"]',
                'textarea[id="CargoDescription"]',
            ],
            desc_val or "",
            "توضیحات کالا",
            required=False,
        )

        # Force form validation update in case some events didn't propagate
        try:
            await self.page.evaluate(
                """() => {
                if (window.jQuery) {
                    const $form = window.jQuery('#frmcommodityInsert');
                    if ($form.length && $form.data('formValidation')) {
                        $form.data('formValidation').validate();
                    }
                }
            }"""
            )
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        await self._click_with_fallback(
            [
                "#btnInsertLoad",
                "button:has-text('ثبت کالای جدید')",
            ],
            "ثبت کالای جدید",
            required=True,
        )
        # Wait for the cargo list grid to be populated (confirms item was saved)
        cargo_row_appeared = await self._wait_for_non_empty_value(
            ["#gridfullLoaddata tr td", "#gridfullLoaddata tr"], timeout_ms=8000
        )
        if cargo_row_appeared is None:
            # Try to extract any form error before giving up
            form_errors = await self._extract_form_errors()
            error_msg = form_errors or "کالا در جدول بارگذاری نشد"
            logger.warning("cargo_grid_not_populated", extra={"extra_fields": {"errors": error_msg}})
            raise WaybillError(f"کالا در جدول بارگذاری نشد: {error_msg}")

        value_val = cargo.get("value")
        await self._fill_verified_text_field(
            [
                "#txtLoadsValue",
                'input[name="txtLoadsValue"]',
                'input[id="txtLoadsValue"]',
            ],
            self._normalize_number_text(value_val or ""),
            "ارزش تقریبی بار",
            required=bool(value_val),
            normalizer=self._digits_only,
        )

        # Click Next and check errors
        cargo_next_clicked = await self._click_step_next(
            4,
            5,
            [
                "#btnGoLVL5",
                "#GoLVL5",
                'button[data-to="#pills-5-tab"]',
            ],
            "مرحله بعد (کالا)",
        )
        if not cargo_next_clicked:
            await self._force_step_transition(5)

        pill5_ready = await self._wait_for_step_marker(
            5,
            ["#ddStateSource", "#ddCitySource", "#txtAddressSource", "#btnGoLVL6"],
            timeout_ms=10000,
        )
        if not pill5_ready:
            form_errors = await self._extract_form_errors()
            error_msg = form_errors or "اعتبارسنجی فرم کالا ناموفق بود"
            logger.error("cargo_form_validation_failed", extra={"extra_fields": {"errors": error_msg}})
            raise WaybillError(f"گذر از مرحله کالا ناموفق بود: {error_msg}")

    async def _fill_origin_info(self, origin_data: dict[str, Any]) -> dict[str, Any]:
        """پر کردن اطلاعات مبدا و گذر به مرحله بعد"""
        origin_result = await self.location_selector.select_location(origin_data, origin=True)
        self._record_selector_inventory(
            field_label="مبدا",
            selectors=["location_selector"],
            status="filled" if origin_result.get("success") else "unsupported",
            selector_used=origin_result.get("method"),
            value=origin_result.get("address") or origin_data.get("address"),
            pill="origin",
        )

        if not origin_result["success"]:
            raise WaybillError(f"انتخاب مبدا با شکست مواجه شد: {origin_result}")

        origin_next_clicked = await self._click_step_next(
            5,
            6,
            [
                "#btnGoLVL6",
                "#GoStepMagsadBtn",
                'button[data-to="#pills-6-tab"]',
            ],
            "مرحله بعد (مبدا)",
        )
        if not origin_next_clicked:
            await self._force_step_transition(6)

        pill6_ready = await self._wait_for_step_marker(
            6,
            ["#ddStateDest", "#ddCityDest", "#txtAddressDest", "#btnGoLVL7"],
            timeout_ms=10000,
        )
        if not pill6_ready:
            form_errors = await self._extract_form_errors()
            error_msg = form_errors or "اعتبارسنجی فرم مبدا ناموفق بود"
            raise WaybillError(f"گذر از مرحله مبدا ناموفق بود: {error_msg}")

        return origin_result

    async def _fill_destination_info(self, destination_data: dict[str, Any]) -> dict[str, Any]:
        """پر کردن اطلاعات مقصد و گذر به مرحله بعد"""
        dest_result = await self.location_selector.select_location(destination_data, origin=False)
        self._record_selector_inventory(
            field_label="مقصد",
            selectors=["location_selector"],
            status="filled" if dest_result.get("success") else "unsupported",
            selector_used=dest_result.get("method"),
            value=dest_result.get("address") or destination_data.get("address"),
            pill="destination",
        )

        if not dest_result["success"]:
            raise WaybillError(f"انتخاب مقصد با شکست مواجه شد: {dest_result}")

        destination_next_clicked = await self._click_step_next(
            6,
            7,
            [
                "#btnGoLVL7",
                "#GoStepPreviewAddressBtn",
                'button[data-to="#pills-7-tab"]',
            ],
            "مرحله بعد (مقصد)",
        )
        if not destination_next_clicked:
            await self._force_step_transition(7)

        pill7_ready = await self._wait_for_step_marker(
            7,
            ["#txtAddressSourceView", "#txtAddressDestView", '#pills-7 button[data-to="#pills-8-tab"]'],
            timeout_ms=10000,
        )
        if not pill7_ready:
            form_errors = await self._extract_form_errors()
            error_msg = form_errors or "اعتبارسنجی فرم مقصد ناموفق بود"
            raise WaybillError(f"گذر از مرحله مقصد ناموفق بود: {error_msg}")

        return dest_result

    async def _handle_tajmi_initialization(self) -> None:
        """آماده‌سازی حالت تجمیعی برای ثبت ناوگان"""
        if await self._element_exists("#DriverListTajmi"):
            logger.info("vehicle_tajmi_mode_detected")
            await self._disable_hidden_required_fields(
                [
                    "#txtDriverSearch",
                    "#driversearchtext",
                    "#pelakFirst",
                    "#pelakCombo",
                    "#pelakCenter",
                    "#pelakIrNum",
                    "#pelakTypeCombo",
                ]
            )
            await self._log_select_options("#PelakComboTajmi", "tajmi_plate")

    async def _fill_vehicle_plate(
        self,
        vehicle: dict[str, str],
        plate_parts: dict[str, str] | None,
        free_zone_parts: dict[str, str] | None,
        tajmi_mode: bool,
    ) -> None:
        """پر کردن پلاک خودرو"""
        if plate_parts or free_zone_parts:
            selected_tajmi = False
            if tajmi_mode:
                if plate_parts:
                    selected_tajmi = await self._select_option_by_fragments(
                        "#PelakComboTajmi",
                        [
                            plate_parts["iran"],
                            plate_parts["letter"],
                            plate_parts["first"],
                            plate_parts["center"],
                        ],
                    )
                elif free_zone_parts:
                    selected_tajmi = await self._select_option_by_fragments(
                        "#PelakComboTajmi",
                        [
                            free_zone_parts["number"],
                            free_zone_parts["zone_name"],
                        ],
                    )
                if not selected_tajmi:
                    selected_tajmi = await self._select_first_non_placeholder_option("#PelakComboTajmi")
            if selected_tajmi:
                try:
                    selected_plate_value = await self.page.eval_on_selector(
                        "#PelakComboTajmi",
                        """el => {
                            if (!el) return '';
                            return String(el.value || '');
                        }""",
                    )
                except Exception:
                    selected_plate_value = ""
                if selected_plate_value:
                    await self._set_select_value_with_js("#PelakComboTajmi", str(selected_plate_value))
                await asyncio.sleep(0.05)
                await self._wait_for_non_empty_value(
                    ["#TypeofLoaderTajmi", "#CapacityTajmi", "#CapacityTajmiTo"],
                    timeout_ms=8000,
                )
            else:
                if plate_parts:
                    if await self._element_exists("#pelakTypeNormal"):
                        await self._click_with_fallback(["#pelakTypeNormal"], "نوع پلاک ملی", required=False)
                    await self._fill_verified_text_field(
                        ['input[id="pelakFirst"]', 'input[name="pelakFirst"]'],
                        plate_parts["first"],
                        "دو رقم ابتدایی پلاک",
                        required=True,
                        normalizer=self._digits_only,
                        prefer_type=True,
                    )
                    await self._select_dropdown_with_fallback(
                        ['select[id="pelakCombo"]', 'select[name="pelakCombo"]'],
                        plate_parts["letter"],
                        "حرف پلاک",
                        required=True,
                    )
                    await self._fill_verified_text_field(
                        ['input[id="pelakCenter"]', 'input[name="pelakCenter"]'],
                        plate_parts["center"],
                        "سه رقم میانی پلاک",
                        required=True,
                        normalizer=self._digits_only,
                        prefer_type=True,
                    )
                    await self._fill_verified_text_field(
                        ['input[id="pelakIrNum"]', 'input[name="pelakIrNum"]'],
                        plate_parts["iran"],
                        "کد ایران پلاک",
                        required=True,
                        normalizer=self._digits_only,
                        prefer_type=True,
                    )
                elif free_zone_parts:
                    if await self._element_exists("#pelakTypeFreeZone"):
                        await self._click_with_fallback(["#pelakTypeFreeZone"], "نوع پلاک منطقه آزاد", required=False)
                    await self._select_dropdown_with_fallback(
                        ['select[id="pelakTypeCombo"]', 'select[name="pelakTypeCombo"]'],
                        free_zone_parts["zone_id"],
                        "منطقه آزاد",
                        required=True,
                    )
                    await self._fill_verified_text_field(
                        ['input[id="pelakAzadFarsiNumber"]', 'input[name="pelakAzadFarsiNumber"]'],
                        free_zone_parts["number"],
                        "شماره پلاک منطقه آزاد",
                        required=True,
                        normalizer=self._digits_only,
                        prefer_type=True,
                    )
                    if free_zone_parts.get("two_digit"):
                        await self._fill_verified_text_field(
                            ['input[id="pelakAzadFarsiNumber3"]', 'input[name="pelakAzadFarsiNumber3"]'],
                            free_zone_parts["two_digit"],
                            "کد دو رقمی منطقه آزاد",
                            required=False,
                            normalizer=self._digits_only,
                            prefer_type=True,
                        )
                await self._click_with_fallback(
                    [
                        "#btnShowDetailspelaq",
                    ],
                    "مشاهده مشخصات پلاک",
                    required=True,
                )
                plate_lookup_value = await self._wait_for_non_empty_value(
                    ["#TypeofLoader", "#CapacityFrom", "#TypeofLoaderTajmi", "#CapacityTajmi"],
                    timeout_ms=8000,
                )
                if plate_lookup_value is None:
                    logger.warning(
                        "plate_details_not_loaded_after_fill",
                        extra={"extra_fields": {"plate": vehicle.get("plate", "")}},
                    )
        else:
            await self._fill_with_fallback(
                [
                    'input[name="PlateNumber"]',
                    'input[id="PlateNumber"]',
                    'input[name*="plate" i]',
                ],
                vehicle.get("plate", ""),
                "پلاک خودرو",
                required=True,
            )

    async def _handle_tajmi_driver_selection(self, driver_code: str) -> bool:
        """انتخاب راننده در حالت تجمیعی"""
        if not await self._element_exists("#DriverListTajmi"):
            return False

        try:
            await self._wait_for_select_options_count("#DriverListTajmi", timeout_ms=12000)
            await self._log_select_options("#DriverListTajmi", "tajmi_driver_after_plate")
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        # Fetch all options first
        try:
            options = await self.page.eval_on_selector_all(
                "#DriverListTajmi option",
                "els => els.map(el => ({text: (el.textContent || '').trim(), value: (el.getAttribute('value') || '').trim()}))",
            )
        except Exception:
            options = []

        selected_driver = False

        # 1. Match by driver_code (national code)
        if driver_code:
            normalized_code = self._normalize_text(driver_code)
            for option in options:
                opt_text = self._normalize_text(option.get("text") or "")
                opt_val = self._normalize_text(option.get("value") or "")
                if normalized_code in opt_text or normalized_code in opt_val:
                    selected_driver = await self._set_select_value_with_js(
                        "#DriverListTajmi", option.get("value") or ""
                    )
                    if selected_driver:
                        logger.info(
                            "vehicle_tajmi_driver_selected_by_code",
                            extra={"extra_fields": {"driver_code": driver_code}},
                        )
                        break

        # 2. Match first non-placeholder option
        if not selected_driver:
            for option in options:
                opt_text = self._normalize_text(option.get("text") or "")
                opt_val = str(option.get("value") or "").strip()
                if opt_text in {"", "انتخاب", "انتخابکنید", "انتخابکنید..."}:
                    continue
                if opt_val in {"", "0"}:
                    continue
                selected_driver = await self._set_select_value_with_js("#DriverListTajmi", option.get("value") or "")
                if selected_driver:
                    logger.info("vehicle_tajmi_driver_selected_first_non_placeholder")
                    break

        # 3. Match any valid option
        if not selected_driver:
            for option in options:
                opt_val = str(option.get("value") or "").strip()
                if not opt_val or opt_val == "0":
                    continue
                selected_driver = await self._set_select_value_with_js("#DriverListTajmi", option.get("value") or "")
                if selected_driver:
                    logger.info("vehicle_tajmi_driver_selected_fallback_any")
                    break

        logger.info(
            "vehicle_tajmi_driver_select_attempt",
            extra={"extra_fields": {"selected": selected_driver, "driver_code": driver_code}},
        )

        await self._wait_for_non_empty_value(
            ["#DriverFullNameTajmi", "#DriverMobileTajmi"],
            timeout_ms=8000,
        )
        return selected_driver

    async def _fill_fallback_driver_info(self, driver_code: str, driver_phone: str) -> None:
        """ثبت اطلاعات راننده در حالت عادی یا در صورت شکست حالت تجمیعی"""
        await self._wait_for_loading_overlays_to_disappear()
        if driver_code:
            await self._fill_verified_text_field(
                [
                    'input[name="txtDriverSearch"]',
                    'input[id="txtDriverSearch"]',
                    'input[name="DriverNationalCode"]',
                ],
                driver_code,
                "کد ملی راننده",
                required=True,
                normalizer=self._normalize_national_code,
                prefer_type=True,
            )
            if await self._is_element_visible("#btnShowDetailsDriver"):
                await self._click_with_fallback(
                    ["#btnShowDetailsDriver"],
                    "مشاهده مشخصات راننده",
                    required=True,
                )
                await self._wait_for_loading_overlays_to_disappear()
            elif await self._is_element_visible("#driversearch"):
                await self._click_with_fallback(
                    ["#driversearch"],
                    "جستجوی راننده",
                    required=True,
                )
                await self._wait_for_loading_overlays_to_disappear()

        if driver_phone:
            await self._fill_verified_text_field(
                [
                    'input[name="DriverPhone"]',
                    'input[id="DriverPhone"]',
                ],
                driver_phone,
                "تلفن راننده",
                required=True,
                normalizer=self._normalize_mobile,
            )

    async def _fill_vehicle_type(self, vehicle_type: str, tajmi_mode: bool = False) -> None:
        """ثبت نوع ناوگان"""
        if vehicle_type:
            is_visible = False
            for selector in ['select[name="VehicleType"]', 'select[id="VehicleType"]']:
                if await self._is_element_visible(selector):
                    is_visible = True
                    break

            if not is_visible:
                if tajmi_mode:
                    logger.info("skipping_vehicle_type_selection_in_tajmi_mode")
                    return

            await self._select_dropdown_with_fallback(
                [
                    'select[name="VehicleType"]',
                    'select[id="VehicleType"]',
                ],
                vehicle_type,
                "نوع ناوگان",
                required=not tajmi_mode,
            )

    async def _fill_vehicle_info(self, vehicle: dict[str, str]):
        """پر کردن اطلاعات ناوگان"""
        await self._wait_for_loading_overlays_to_disappear()
        await self._wait_for_step_marker(
            3, ["#txtDriverSearch", "#PelakComboTajmi", "#DriverListTajmi"], timeout_ms=8000
        )
        tajmi_mode = await self._element_exists("#PelakComboTajmi") or await self._element_exists("#DriverListTajmi")

        driver_code = self._normalize_national_code(vehicle.get("driver_national_code", ""))
        driver_phone = self._normalize_mobile(vehicle.get("driver_phone", ""))

        plate_str = vehicle.get("plate", "")
        plate_parts = self._parse_plate(plate_str)
        free_zone_parts = self._parse_free_zone_plate(plate_str)
        await self._fill_vehicle_plate(
            vehicle, plate_parts=plate_parts, free_zone_parts=free_zone_parts, tajmi_mode=tajmi_mode
        )

        if tajmi_mode:
            selected_driver = await self._handle_tajmi_driver_selection(driver_code)
            if not selected_driver:
                logger.warning("vehicle_tajmi_driver_selection_failed_trying_normal")
                await self._fill_fallback_driver_info(driver_code, driver_phone)
        else:
            await self._fill_fallback_driver_info(driver_code, driver_phone)

        await self._fill_vehicle_type(vehicle.get("type", ""), tajmi_mode=tajmi_mode)

        # Click Next and verify transition to pill 4
        vehicle_next = await self._click_step_next(
            3,
            4,
            ["#btnGoLVL4", "#GoLVL4", 'button[data-to="#pills-4-tab"]'],
            "مرحله بعد (ناوگان)",
        )
        if not vehicle_next:
            await self._force_step_transition(4)

        pill4_ready = await self._wait_for_step_marker(
            4,
            ["#txtLoadsValue", "#btnAddLoad", "#btnGoLVL5"],
            timeout_ms=15000,
        )
        if not pill4_ready:
            form_errors = await self._extract_form_errors()
            if not form_errors:
                # Sometimes toasts take a moment to appear
                await self.page.wait_for_timeout(2000)
                form_errors = await self._extract_form_errors()

            error_msg = form_errors or "اعتبارسنجی فرم ناوگان ناموفق بود یا سرور پاسخی نداد"
            logger.error("vehicle_form_validation_blocked", extra={"extra_fields": {"errors": error_msg}})
            raise WaybillError(f"گذر از مرحله ناوگان ناموفق بود: {error_msg}")

    async def _fill_financial_info(self, financial: dict[str, Any]):
        """پر کردن اطلاعات مالی"""
        await self._wait_for_loading_overlays_to_disappear()
        if financial.get("cost"):
            await self._fill_with_fallback(
                [
                    'input[name="TransportCost"]',
                    'input[id="TransportCost"]',
                    'input[name="txtkeraye"]',
                    'input[id="txtkeraye"]',
                    'input[name="txtPishKeraye"]',
                    'input[id="txtPishKeraye"]',
                    'input[name="txtPasKeraye"]',
                    'input[id="txtPasKeraye"]',
                    'input[name*="transport" i][name*="cost" i]',
                    'input[name*="price" i]',
                ],
                self._normalize_number_text(financial["cost"]),
                "هزینه حمل",
                required=True,
            )

        current_time = datetime.now().strftime("%H:%M")
        await self._fill_verified_text_field(
            [
                'input[name="loadingTime"]',
                'input[id="loadingTime"]',
            ],
            current_time,
            "ساعت شروع حمل",
            required=False,
            prefer_type=True,
        )

        if financial.get("payment_method"):
            selected = await self._select_dropdown_with_fallback(
                [
                    'select[name="PaymentMethod"]',
                    'select[id="PaymentMethod"]',
                    'select[name*="payment" i][name*="method" i]',
                ],
                financial["payment_method"],
                "روش پرداخت",
                required=False,
            )
            if not selected:
                await self._fill_with_fallback(
                    [
                        'input[name="PaymentMethod"]',
                        'input[id="PaymentMethod"]',
                        'input[name*="payment" i]',
                    ],
                    str(financial["payment_method"]),
                    "روش پرداخت",
                    required=False,
                )

    async def _fill_shipping_options(self, shipping_opts: dict[str, Any]):
        """مدیریت گزینه‌های حمل (two_way، end_shipping، time_limit)"""
        if not isinstance(shipping_opts, dict):
            return

        if shipping_opts.get("two_way"):
            await self._check_checkbox_with_fallback(
                [
                    "input[name='TwoWay']",
                    "input[id='TwoWay']",
                    "input[name='two_way']",
                    "input[type='checkbox'][name*='way' i]",
                ],
                "ثبت دو طرفه",
            )
        if shipping_opts.get("end_shipping"):
            await self._fill_with_fallback(
                [
                    "input[name='EndShipping']",
                    "input[id='EndShipping']",
                    "input[name='end_shipping']",
                    "input[name='txtEndShipping']",
                    "input[id='txtEndShipping']",
                ],
                str(shipping_opts["end_shipping"]),
                "تاریخ پایان حمل",
                required=False,
            )
        if shipping_opts.get("time_limit"):
            await self._fill_with_fallback(
                [
                    "input[name='TimeLimit']",
                    "input[id='TimeLimit']",
                    "input[name='time_limit']",
                    "input[name='txtTimeLimit']",
                    "input[id='txtTimeLimit']",
                ],
                str(shipping_opts["time_limit"]),
                "محدودیت زمانی",
                required=False,
            )

    async def _check_checkbox_with_fallback(
        self,
        selectors: list,
        label: str,
    ) -> bool:
        """فعال کردن checkbox با چند selector جایگزین (از check() استفاده می‌کند نه click())."""
        found_checkbox = False
        for selector in selectors:
            try:
                locator = await self.page.query_selector(selector)
                if locator is None:
                    continue
                found_checkbox = True
                is_checked = await resolve_maybe_awaitable(locator.is_checked())
                if not is_checked:
                    await locator.check()
                    await asyncio.sleep(0.05)
                self._record_selector_inventory(
                    field_label=label,
                    selectors=list(selectors),
                    status="filled",
                    selector_used=selector,
                    value="checked",
                )
                return True
            except Exception:
                found_checkbox = True
                break

        for selector in selectors:
            try:
                label_sel = f"label:has({selector})"
                label_locator = await self.page.query_selector(label_sel)
                if label_locator is None and found_checkbox:
                    label_locator = await self.smart_locator.locate(self.page, [label_sel], timeout=1200)
                if label_locator is None:
                    continue
                await label_locator.click()
                await asyncio.sleep(0.05)
                self._record_selector_inventory(
                    field_label=label,
                    selectors=list(selectors),
                    status="fallback-only",
                    selector_used=label_sel,
                    value="checked",
                )
                return True
            except Exception:
                continue
        self._record_selector_inventory(
            field_label=label,
            selectors=list(selectors),
            status="unsupported",
            value="unchecked",
        )
        logger.warning(
            "checkbox_not_found",
            extra={"extra_fields": {"field": label, "selectors": selectors}},
        )
        return False

    async def _fill_with_fallback(
        self,
        selectors,
        value: str,
        field_label: str,
        required: bool = True,
    ):
        """تلاش ترتیبی برای پر کردن فیلد با چند selector جایگزین."""
        if not value:
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="skipped",
                value=value,
            )
            return

        try:
            locator = await self.smart_locator.locate(self.page, list(selectors), timeout=5000)
            await locator.fill(value)
            # Dispatch change/input events so cascading form logic (e.g. province→city) triggers
            try:
                await locator.evaluate(
                    "el => { "
                    "el.dispatchEvent(new Event('keydown', { bubbles: true })); "
                    "el.dispatchEvent(new Event('input', { bubbles: true })); "
                    "el.dispatchEvent(new Event('keyup', { bubbles: true })); "
                    "el.dispatchEvent(new Event('change', { bubbles: true })); "
                    "if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change'); } "
                    "}"
                )
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)
            await asyncio.sleep(0.05)
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="filled",
                selector_used=list(selectors)[0] if selectors else None,
                value=value,
            )
            return
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        for selector in selectors:
            fill_success = await self.interactor.safe_fill(selector, value)
            if fill_success:
                await asyncio.sleep(0.05)
                self._record_selector_inventory(
                    field_label=field_label,
                    selectors=list(selectors),
                    status="fallback-only",
                    selector_used=selector,
                    value=value,
                )
                return

            js_success = await self._set_value_with_js(selector, value)
            if js_success:
                await asyncio.sleep(0.05)
                self._record_selector_inventory(
                    field_label=field_label,
                    selectors=list(selectors),
                    status="fallback-only",
                    selector_used=selector,
                    value=value,
                )
                return

        if required:
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="unsupported",
                value=value,
            )
            raise WaybillError(f"پر کردن فیلد `{field_label}` ناموفق بود")

        self._record_selector_inventory(
            field_label=field_label,
            selectors=list(selectors),
            status="unsupported",
            value=value,
        )
        logger.warning(
            "optional_fill_not_found",
            extra={
                "extra_fields": {
                    "field": field_label,
                    "value": str(value),
                    "selectors": list(selectors),
                }
            },
        )

    async def _select_dropdown_with_fallback(
        self,
        selectors,
        value: str,
        field_label: str,
        required: bool = True,
    ):
        """تلاش ترتیبی برای انتخاب گزینه از چند selector."""
        if not value:
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="skipped",
                value=value,
            )
            return False

        for selector in selectors:
            selected = await self._select_dropdown(selector, value)
            if selected:
                status = "filled" if selector == list(selectors)[0] else "fallback-only"
                self._record_selector_inventory(
                    field_label=field_label,
                    selectors=list(selectors),
                    status=status,
                    selector_used=selector,
                    value=value,
                )
                return True

        if required:
            self._record_selector_inventory(
                field_label=field_label,
                selectors=list(selectors),
                status="unsupported",
                value=value,
            )
            raise WaybillError(f"انتخاب `{field_label}` ناموفق بود")

        self._record_selector_inventory(
            field_label=field_label,
            selectors=list(selectors),
            status="unsupported",
            value=value,
        )
        logger.warning(
            "optional_dropdown_not_found",
            extra={"extra_fields": {"field": field_label, "value": value}},
        )
        return False

    async def _select_dropdown(self, selector: str, value: str) -> bool:
        """انتخاب از منوی کشویی"""
        value_text = str(value).strip()
        normalized_target = self._normalize_text(value_text)
        locator = None
        try:
            locator = await self.smart_locator.locate(self.page, [selector], timeout=1200)
        except Exception:
            locator = None

        if locator is None:
            return False

        try:
            await locator.select_option(label=value_text)
            return True
        except Exception:
            try:
                await locator.select_option(value=value_text)
                return True
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)

        try:
            options = await self.page.eval_on_selector_all(
                f"{selector} option",
                "els => els.map(el => ({text: (el.textContent || '').trim(), value: (el.getAttribute('value') || '').trim()}))",
            )
        except Exception:
            options = []

        best_value = None
        for option in options:
            option_text = str(option.get("text") or "").strip()
            option_value = str(option.get("value") or "").strip()

            normalized_text = self._normalize_text(option_text)
            normalized_value = self._normalize_text(option_value)

            if normalized_target == normalized_text or normalized_target == normalized_value:
                best_value = option_value or option_text
                break
            if (
                normalized_target in normalized_text
                or normalized_target in normalized_value
                or normalized_text in normalized_target
            ):
                best_value = option_value or option_text

        if best_value:
            try:
                if locator is not None:
                    await locator.select_option(value=best_value)
                else:
                    await self.page.select_option(selector, value=best_value)

                # Trigger events for formValidation and cascading logic
                try:
                    target_locator = locator if locator is not None else self.page.locator(selector)
                    await target_locator.evaluate(
                        "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }"
                    )
                except Exception:
                    logger.warning("waybill_enhanced_silent_error", exc_info=True)
                return True
            except Exception:
                try:
                    if locator is not None:
                        await locator.select_option(label=best_value)
                    else:
                        await self.page.select_option(selector, label=best_value)

                    try:
                        target_locator = locator if locator is not None else self.page.locator(selector)
                        await target_locator.evaluate(
                            "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }"
                        )
                    except Exception:
                        logger.warning("waybill_enhanced_silent_error", exc_info=True)
                    return True
                except Exception:
                    logger.warning("waybill_enhanced_silent_error", exc_info=True)

        try:
            if await self._set_select_value_with_js(selector, value_text):
                return True
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        if best_value:
            try:
                if await self._set_select_value_with_js(selector, best_value):
                    return True
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)

        return False

    async def _detect_otp_required(self, submit_state: dict[str, Any] | None = None) -> bool:
        """تشخیص نیاز به OTP پس از ارسال فرم"""
        if isinstance(submit_state, dict) and "is_otp_needed" in submit_state:
            return bool(submit_state.get("is_otp_needed"))

        otp_selectors = [
            ".modal.show #otp",
            ".modal.show input[name='otp']",
            ".modal.show .otp-box",
            "input[name='otp']",
            "input[id='otp']",
            "#submitOtp",
        ]
        for selector in otp_selectors:
            if await self._is_selector_visible(selector):
                return True

        try:
            modal_open = await self.page.evaluate(
                "() => !!(document.body && document.body.classList.contains('modal-open'))"
            )
            if modal_open and await self._is_selector_visible("#submitOtp"):
                return True
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)
        return False

    async def _fill_otp_value(self, otp_value: str) -> bool:
        normalized = self._normalize_captcha_solution(otp_value)
        if not normalized:
            return False

        hidden_filled = False
        for selector in ("input[name='otp']", "input[id='otp']", "#otp"):
            if await self._fill_with_selector(selector, normalized):
                hidden_filled = True
                break

        try:
            box_count = await self.page.eval_on_selector_all(".otp-box", "els => els.length")
        except Exception:
            box_count = 0

        if box_count:
            digits = list(normalized)
            if len(digits) == int(box_count):
                try:
                    await self.page.evaluate(
                        """(values) => {
                            const boxes = Array.from(document.querySelectorAll('.otp-box'));
                            boxes.forEach((el, idx) => {
                                const value = String(values[idx] || '');
                                el.value = value;
                                el.dispatchEvent(new Event('input', { bubbles: true }));
                                el.dispatchEvent(new Event('change', { bubbles: true }));
                                if (window.jQuery) {
                                    window.jQuery(el).trigger('input').trigger('change');
                                }
                            });
                        }""",
                        digits,
                    )
                    return True
                except Exception:
                    return hidden_filled

        return hidden_filled

    async def _handle_otp_if_required(
        self,
        otp_value: str | None = None,
        submit_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        مدیریت OTP در صورت نیاز.
        اگر otp_value داده شده باشد آن را وارد می‌کند؛ در غیر این صورت منتظر ورود دستی می‌ماند.
        """
        if not await self._detect_otp_required(submit_state=submit_state):
            return {"success": True, "handled": False, "document_id": (submit_state or {}).get("document_id")}

        otp_selectors = [
            ".modal.show input[name='otp']",
            ".modal.show input[id='otp']",
            "input[name='otp']",
            "input[id='otp']",
            ".otp-box",
        ]

        otp_selector = None
        for selector in otp_selectors:
            try:
                await self.smart_locator.locate(self.page, [selector], timeout=1200)
                otp_selector = selector
                break
            except Exception:
                continue

        if not otp_selector:
            logger.warning("otp_field_not_found", extra={"extra_fields": {}})
            return {"success": False, "handled": True, "document_id": (submit_state or {}).get("document_id")}

        if otp_value:
            filled = await self._fill_otp_value(otp_value)
            if not filled:
                logger.warning("otp_fill_failed", extra={"extra_fields": {"selector": otp_selector}})
                return {"success": False, "handled": True, "document_id": (submit_state or {}).get("document_id")}

            otp_timeout_ms = min(max(10000, utcms_config.PAGE_NAVIGATION_TIMEOUT), 30000)
            otp_response_task = await self._wait_for_response_match(
                lambda response: "IssueDocumentByOtpNew" in (getattr(response, "url", "") or ""),
                timeout_ms=otp_timeout_ms,
            )
            # کلیک تایید OTP
            otp_submit_selectors = [
                "#submitOtp",
                "button:has-text('تایید')",
                "button:has-text('ارسال')",
                "button[type='submit']",
            ]
            for sel in otp_submit_selectors:
                try:
                    element = await self.smart_locator.locate(self.page, [sel], timeout=1200)
                    await element.click()
                    await self._wait_for_network_settle(primary_timeout_ms=otp_timeout_ms, fallback_sleep_seconds=1.5)
                    payload = await self._consume_json_response(
                        otp_response_task,
                        timeout_seconds=max(10.0, otp_timeout_ms / 1000),
                    )
                    otp_state = self._parse_otp_submit_payload(payload)
                    if otp_state is None:
                        # اگر پاسخ AJAX نیامد، به این معنی نیست که OTP تایید شده
                        logger.warning(
                            "otp_response_missing",
                            extra={"extra_fields": {"action": "retry_otp"}},
                        )
                        return {
                            "success": False,
                            "handled": True,
                            "document_id": (submit_state or {}).get("document_id"),
                            "message": "پاسخ سرور برای تایید OTP دریافت نشد",
                        }
                    if otp_state["success"]:
                        return {
                            "success": True,
                            "handled": True,
                            "document_id": otp_state.get("document_id") or (submit_state or {}).get("document_id"),
                        }
                    self.last_error = otp_state["message"] or "ارسال OTP ناموفق بود"
                    return {"success": False, "handled": True, "document_id": otp_state.get("document_id")}
                except Exception:
                    continue
            return {
                "success": False,
                "handled": True,
                "document_id": (submit_state or {}).get("document_id"),
                "message": "ارسال کد OTP انجام نشد",
            }

        # انتظار برای ورود دستی OTP
        if utcms_config.HEADLESS:
            raise WaybillError(
                "ثبت بارنامه نیاز به OTP دارد. در حالت HEADLESS امکان ورود دستی وجود ندارد. "
                "کد OTP را از طریق پارامتر shipping_options.otp ارسال کنید."
            )

        timeout_seconds = max(60, utcms_config.UTCMS_MANUAL_CAPTCHA_TIMEOUT_SECONDS)
        poll_seconds = max(0.5, utcms_config.UTCMS_MANUAL_CAPTCHA_POLL_SECONDS)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        logger.info("otp_waiting_for_manual_input", extra={"extra_fields": {"timeout": timeout_seconds}})

        while asyncio.get_running_loop().time() < deadline:
            try:
                value = await self.page.eval_on_selector(
                    otp_selector,
                    "el => (el.value || '').trim()",
                )
                if value:
                    return {"success": True, "handled": True, "document_id": (submit_state or {}).get("document_id")}
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)
            await asyncio.sleep(poll_seconds)

        raise WaybillError("OTP در بازه زمانی مجاز وارد نشد")

    async def _submit_waybill(self, otp_value: str | None = None, job_id: str | None = None) -> dict[str, Any]:
        """ثبت فرم بارنامه (با پشتیبانی OTP و captcha + Self-Healing)"""

        # ── Self-Healing wrapper for critical interactions ──
        async def resilient_click(
            selectors: list[str],
            label: str,
            *,
            max_retries: int = 3,
            wait_after: float = 0.4,
        ) -> bool:
            """Click with exponential backoff retry + overlay dismissal."""
            for attempt in range(1, max_retries + 1):
                try:
                    if await self._click_with_fallback(
                        selectors,
                        label,
                        required=False,
                        wait_after_seconds=wait_after,
                    ):
                        return True
                except Exception:
                    logger.warning("waybill_enhanced_silent_error", exc_info=True)

                # Check & close blocking overlays
                await self._close_blocking_overlays()

                # Exponential backoff: T_wait(k) = 2^k * 1000ms
                if attempt < max_retries:
                    wait_ms = (2**attempt) * 1000
                    logger.warning(
                        "resilient_click_retry",
                        extra={"extra_fields": {"label": label, "attempt": attempt, "wait_ms": wait_ms}},
                    )
                    await asyncio.sleep(wait_ms / 1000)

            logger.error(
                "resilient_click_failed",
                extra={"extra_fields": {"label": label, "selectors": selectors}},
            )
            return False

        # ── Step 1: Click "مرحله نهایی" ──
        await resilient_click(
            [
                "#btnregisterbarname",
                "#GoFinalStep",
                "button:has-text('مرحله نهایی')",
                "button:has-text('ثبت بارنامه')",
                "button:has-text('ثبت بارنامه')",
                "button:has-text('ادامه')",
            ],
            "مرحله نهایی",
            wait_after=0.5,
            max_retries=1,
        )

        # ── Step 1.5: Wait for final stage loading ──
        try:
            await self.page.locator("#btnRegisterFinished").first.wait_for(state="visible", timeout=8000)
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        # ── Step 2: Solve captcha (if present) ──
        await self._handle_submit_captcha_if_present()

        # ── Step 3: Final submit click ──
        submit_selectors = [
            "#btnRegisterFinished",
            "#btnFinalSubmit",
            "#btnSubmit",
            "button[type='submit']:not([id*='otp' i]):not([id*='Otp'])",
            "input[type='submit']",
            "button:has-text('تایید و ثبت')",
            "button:has-text('ثبت نهایی')",
            "button:has-text('ثبت')",
            "button:has-text('تایید')",
            "#GoFinalStep",
        ]

        submit_timeout_ms = min(max(12000, utcms_config.PAGE_NAVIGATION_TIMEOUT), 35000)
        submit_response_task = await self._wait_for_response_match(
            lambda response: "UpdateRegisterNewOld" in (getattr(response, "url", "") or ""),
            timeout_ms=submit_timeout_ms,
        )

        submit_clicked = await resilient_click(submit_selectors, "ثبت نهایی", wait_after=0.5)
        if not submit_clicked:
            raise WaybillError("ارسال فرم بارنامه انجام نشد (کلیک روی دکمه ثبت ناموفق بود)")

        await self._wait_for_network_settle(primary_timeout_ms=submit_timeout_ms, fallback_sleep_seconds=2.0)
        await asyncio.sleep(0.1)

        submit_payload = await self._consume_json_response(
            submit_response_task,
            timeout_seconds=max(12.0, submit_timeout_ms / 1000),
        )
        submit_state = self._parse_register_submit_payload(submit_payload)
        if submit_state is not None and not submit_state["success"]:
            raise WaybillError(submit_state["message"] or "ارسال فرم بارنامه ناموفق بود")

        # ── Step 4: OTP Handling ──
        otp_state = await self._handle_otp_if_required(otp_value, submit_state=submit_state)
        if not otp_state["success"]:
            raise WaybillError("مدیریت OTP ناموفق بود")

        if await self._detect_otp_required(submit_state=submit_state):
            await self._wait_for_network_settle(primary_timeout_ms=12000, fallback_sleep_seconds=2.0)

        # ── Step 5: OTP Detect & Graceful Exit (Self-Healing) ──
        # After successful submit, check if an OTP/SMS challenge appeared.
        # If OTP modal is detected → graceful exit with OTP_BACKOFF status.
        # If NOT detected → submission was successful, proceed normally.
        otp_backoff_result = await self._check_otp_after_submit()
        if otp_backoff_result is not None:
            return otp_backoff_result

        # ── Step 6: Extract tracking code ──
        document_id = (otp_state or {}).get("document_id") or (submit_state or {}).get("document_id")
        tracking_code = await self._extract_tracking_code(document_id=document_id)
        submission_confirmed = await self._is_submission_successful()

        # CRITICAL SECURITY FIX: To prevent false positives where waybills are marked
        # as "Successful Registration" without actually being registered in UTCMS,
        # we require a valid tracking code to be extracted to confirm success.
        if not tracking_code:
            logger.warning(
                "submit_tracking_code_missing_confirm_false",
                extra={"extra_fields": {"job_id": job_id, "submission_confirmed": submission_confirmed}},
            )
            submission_confirmed = False

        if not tracking_code and not submission_confirmed:
            import os
            import time

            try:
                debug_dir = "/app/output/screenshots/debug"
                os.makedirs(debug_dir, exist_ok=True)
                ts = int(time.time())
                debug_html_path = os.path.join(debug_dir, f"{job_id or 'unknown'}_{ts}.html")
                debug_png_path = os.path.join(debug_dir, f"{job_id or 'unknown'}_{ts}.png")

                html_content = await self.page.content()
                with open(debug_html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                await self.page.screenshot(path=debug_png_path, full_page=True)
                logger.error(f"Saved submit failure debug info to {debug_html_path} and {debug_png_path}")
            except Exception as e:
                logger.error(f"Failed to save debug info: {e}")

            form_errors = await self._extract_form_errors()
            if form_errors:
                raise WaybillError(f"ثبت بارنامه با خطا مواجه شد: {form_errors}")
            raise WaybillError("ثبت بارنامه تایید نشد: نه کد رهگیری پیدا شد و نه نشانه موفقیت در صفحه وجود داشت")

        # Capture waybill screenshot on success
        waybill_screenshot = None
        if tracking_code or submission_confirmed:
            import os
            import time

            try:
                screenshots_dir = "app/ui/assets/screenshots"
                os.makedirs(screenshots_dir, exist_ok=True)
                screenshot_filename = f"{job_id or 'unknown_' + str(int(time.time()))}.png"
                screenshot_path = os.path.join(screenshots_dir, screenshot_filename)

                await self.page.screenshot(path=screenshot_path, full_page=True)
                waybill_screenshot = f"/assets/screenshots/{screenshot_filename}"
                logger.info(f"Successfully saved waybill screenshot to {screenshot_path}")
            except Exception as e:
                logger.error(f"Failed to capture waybill screenshot: {e}", exc_info=True)

        return {
            "success": True,
            "status": "submitted",
            "tracking_code": tracking_code,
            "url": await self._current_url(),
            "waybill_screenshot": waybill_screenshot,
        }

    async def _wait_for_loading_overlays_to_disappear(self, timeout_ms: int = 15000) -> None:
        """Wait for Iranian government style 'لطفا صبر کنید' or other loading masks to disappear."""
        # Use single browser-side JS evaluation to avoid multiple Py-JS roundtrips for 15+ selectors.
        js_check = """
        () => {
            const selectors = [
                ".loading", ".spinner", ".k-loading-mask", ".k-loading-image", ".k-loading-color",
                "#loading", "#loading-box", ".loading-overlay", ".loading-mask", "div.modal-backdrop",
                ".blockUI", ".blockMsg", ".blockPage"
            ];
            for (const sel of selectors) {
                try {
                    const els = document.querySelectorAll(sel);
                    for (const el of els) {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                            return true;
                        }
                    }
                } catch (e) {}
            }
            try {
                const xpathResult = document.evaluate(
                    "//div[contains(., 'لطفا صبر کنید') or contains(., 'در حال بارگذاری')]",
                    document,
                    null,
                    XPathResult.ORDERED_NODE_SNAPSHOT_TYPE,
                    null
                );
                for (let i = 0; i < xpathResult.snapshotLength; i++) {
                    const el = xpathResult.snapshotItem(i);
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    if (style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0) {
                        return true;
                    }
                }
            } catch (e) {}
            return false;
        }
        """

        deadline = asyncio.get_running_loop().time() + (timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            try:
                found_any = await self.page.evaluate(js_check)
            except Exception:
                found_any = False

            if not found_any:
                return

            await asyncio.sleep(0.05)

        # Overlay still present after timeout — log and continue (don't block the flow)
        logger.warning(
            "loading_overlay_timeout",
            extra={"extra_fields": {"timeout_ms": timeout_ms, "action": "continuing_despite_overlay"}},
        )

    async def _close_blocking_overlays(self) -> None:
        """Attempt to close blocking overlays (modals, popups, backdrops)."""
        try:
            await self.page.evaluate(
                """() => {
                // Close modal backdrops
                const backdrops = document.querySelectorAll('div.modal-backdrop, .modal-backdrop, .overlay, .popup-overlay');
                backdrops.forEach(el => el.remove());
                // Close modals
                const modals = document.querySelectorAll('.modal.show, .modal.active, div[role="dialog"]');
                modals.forEach(el => {
                    el.classList.remove('show', 'active');
                    el.style.display = 'none';
                });
                // Click any close/back buttons
                const closeBtns = document.querySelectorAll('.modal .close, .modal-close, button.close, [data-dismiss="modal"]');
                closeBtns.forEach(btn => btn.click());
            }"""
            )
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

    async def _check_otp_after_submit(self) -> dict[str, Any] | None:
        """
        Detect OTP modal after submit. If found, gracefully exit and return OTP_BACKOFF status.
        The worker will calculate T_now + 60 minutes and update the DB.
        Timeout increased from 5s to 15s to avoid false negatives on slow OTP modals.
        """
        otp_selectors = "input#sms-code, div.otp-challenge, #submitOtp, input[name='otp'], .otp-box"

        try:
            candidate = await self.page.wait_for_selector(otp_selectors, timeout=15000)
            if candidate is None:
                return None
            if candidate is not None:
                try:
                    visible = await resolve_maybe_awaitable(candidate.is_visible())
                    if not isinstance(visible, bool):
                        visible = bool(visible)
                    if not visible:
                        return None
                except Exception:
                    return None

            # OTP modal detected → graceful exit
            logger.warning(
                "otp_challenge_detected_after_submit",
                extra={"extra_fields": {"action": "graceful_exit", "retry_after_minutes": 60}},
            )

            # Note: context cleanup is handled by the caller (worker's managed_browser_session / finally block)
            return {
                "success": False,
                "status": "OTP_BACKOFF",
                "next_retry_at_minutes_add": 60,
                "message": "OTP challenge detected. Bot exited gracefully for manual or delayed retry.",
            }
        except Exception:
            # TimeoutError → OTP modal NOT detected → submission was successful
            return None

    def _normalize_captcha_solution(self, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = str(value).strip().translate(self._captcha_digit_map)
        if not normalized:
            return None

        normalized = normalized.replace(" ", "").replace("=", "").replace("؟", "").replace("?", "")
        if any(token in normalized for token in ("+", "-", "*", "/", "x", "X", "×", "÷")):
            decision = captcha_engine.solve_text_with_confidence(normalized)
            min_confidence = self._captcha_math_min_confidence()
            if decision.value and decision.confidence >= min_confidence:
                normalized = str(decision.value).translate(self._captcha_digit_map).strip()
            else:
                return None

        if not self._captcha_value_pattern.match(normalized):
            return None

        min_len = max(1, utcms_config.CAPTCHA_VALUE_MIN_LENGTH)
        max_len = max(min_len, utcms_config.CAPTCHA_VALUE_MAX_LENGTH)
        if not (min_len <= len(normalized) <= max_len):
            return None

        return normalized

    def _captcha_math_min_confidence(self) -> float:
        return max(0.0, min(1.0, float(utcms_config.CAPTCHA_MATH_MIN_CONFIDENCE)))

    def _hint_candidates_from_text(self, raw_text: str | None) -> list[str]:
        text = (raw_text or "").strip()
        if not text:
            return []

        candidates: list[str] = []
        full_text = " ".join(text.split())
        if full_text:
            candidates.append(full_text)

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            lower_line = line.lower()
            if any(marker in lower_line for marker in self._captcha_hint_markers):
                candidates.append(line)

        for fragment in re.findall(r"[^\n]{0,40}[+\-*/×÷][^\n]{0,40}", text):
            cleaned = " ".join(fragment.split())
            if cleaned:
                candidates.append(cleaned)

        unique: list[str] = []
        seen = set()
        for item in candidates:
            normalized = item.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(item)
        return unique

    async def _extract_submit_captcha_hints(self, captcha_selector: str) -> list[str]:
        candidates: list[str] = []
        hint_selectors = (
            "label[for='DNTCaptchaInputText']",
            "#dntCaptcha",
            ".dntCaptcha",
            ".captcha",
            ".captcha-container",
        )
        for selector in hint_selectors:
            try:
                text = await self.page.eval_on_selector(
                    selector,
                    "el => ((el.innerText || el.textContent || '').trim())",
                )
                cleaned = await self._as_clean_text(text)
                if cleaned:
                    candidates.extend(self._hint_candidates_from_text(cleaned))
            except Exception:
                continue

        try:
            around_input = await self.page.eval_on_selector(
                captcha_selector,
                """el => {
                    if (!el) return '';
                    const parent = el.closest('form, .captcha, .captcha-container, .form-group') || el.parentElement;
                    return (parent && (parent.innerText || parent.textContent)) ? (parent.innerText || parent.textContent) : '';
                }""",
            )
            cleaned = await self._as_clean_text(around_input)
            if cleaned:
                candidates.extend(self._hint_candidates_from_text(cleaned))
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        try:
            body_text = await self.page.evaluate("() => ((document.body && document.body.innerText) || '')")
            cleaned = await self._as_clean_text(body_text)
            if cleaned:
                candidates.extend(self._hint_candidates_from_text(cleaned[:1500]))
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        unique: list[str] = []
        seen = set()
        for item in candidates:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)

        return unique

    def _is_plausible_captcha_image(self, box: dict) -> bool:
        width = float(box.get("width") or 0)
        height = float(box.get("height") or 0)
        if width < 35 or height < 18:
            return False
        if width > 220 or height > 120:
            return False
        aspect_ratio = width / max(height, 1.0)
        return 1.0 <= aspect_ratio <= 5.5

    def _captcha_image_score(self, box: dict, input_box: dict | None, selector: str) -> float:
        width = float(box.get("width") or 0)
        height = float(box.get("height") or 0)
        score = 200.0 - abs(width - 110.0) - abs(height - 40.0)
        lowered = selector.lower()
        if "dnt" in lowered:
            score += 20
        if "captcha" in lowered:
            score += 10

        if input_box:
            image_center_x = float(box.get("x") or 0) + (width / 2.0)
            image_center_y = float(box.get("y") or 0) + (height / 2.0)
            input_center_x = float(input_box.get("x") or 0) + (float(input_box.get("width") or 0) / 2.0)
            input_center_y = float(input_box.get("y") or 0) + (float(input_box.get("height") or 0) / 2.0)
            score -= abs(image_center_x - input_center_x) * 0.35
            score -= abs(image_center_y - input_center_y) * 0.85
        return score

    async def _extract_captcha_image_base64(self, captcha_selector: str | None = None) -> str | None:
        input_box = None
        if captcha_selector:
            try:
                captcha_input = await self.smart_locator.locate(self.page, [captcha_selector], timeout=900)
                input_box = await captcha_input.bounding_box()
            except Exception:
                input_box = None

        best_candidate = None
        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                locators = self.page.locator(selector)
                count = await locators.count()
            except Exception:
                continue

            for index in range(count):
                try:
                    locator = locators.nth(index)
                    box = await locator.bounding_box()
                    if not box or not self._is_plausible_captcha_image(box):
                        continue
                    score = self._captcha_image_score(box, input_box, selector)
                    if best_candidate is None or score > best_candidate[0]:
                        best_candidate = (score, locator)
                except Exception:
                    continue

        if best_candidate is None:
            # Fallback to simple query if complex locator failed
            for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
                try:
                    element = await self.smart_locator.locate(self.page, [selector], timeout=1500)
                    image_bytes = await element.screenshot(type="png")
                    if image_bytes:
                        return base64.b64encode(image_bytes).decode("utf-8")
                except Exception:
                    continue
            return None

        try:
            image_bytes = await best_candidate[1].screenshot(type="png")
            if image_bytes:
                return base64.b64encode(image_bytes).decode("utf-8")
        except Exception:
            return None

        return None

    def _save_captcha_debug_artifact(
        self,
        image_base64: str,
        phase: str,
        attempt: int | None,
        stage: str,
        provider: str | None = None,
        solution: str | None = None,
        error: str | None = None,
    ) -> None:
        import binascii
        import json
        import os
        import re
        from datetime import UTC, datetime
        from pathlib import Path

        if not utcms_config.CAPTCHA_DEBUG_SAVE_IMAGES or not image_base64:
            return
        try:
            image_bytes = base64.b64decode(image_base64, validate=True)
        except (ValueError, binascii.Error):
            return

        timestamp = datetime.now(UTC).replace(tzinfo=None).strftime("%Y%m%d-%H%M%S-%f")
        safe_phase = re.sub(r"[^a-zA-Z0-9_-]+", "_", phase or "submit")
        safe_stage = re.sub(r"[^a-zA-Z0-9_-]+", "_", stage or "capture")
        debug_dir = Path(utcms_config.CAPTCHA_DEBUG_DIR)
        debug_dir.mkdir(parents=True, exist_ok=True)

        base_name = f"{timestamp}-{safe_phase}-a{attempt or 0}-{safe_stage}"
        image_path = debug_dir / f"{base_name}.png"
        meta_path = debug_dir / f"{base_name}.json"

        image_path.write_bytes(image_bytes)
        meta_path.write_text(
            json.dumps(
                {
                    "saved_at": datetime.now(UTC).replace(tzinfo=None).isoformat() + "Z",
                    "phase": phase,
                    "attempt": attempt,
                    "stage": stage,
                    "provider": provider,
                    "solution": solution,
                    "error": error,
                    "url": getattr(self.page, "url", ""),
                    "image_path": os.fspath(image_path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        logger.info(
            "captcha_debug_saved",
            extra={
                "extra_fields": {
                    "image_path": os.fspath(image_path),
                    "meta_path": os.fspath(meta_path),
                    "phase": phase,
                    "attempt": attempt,
                    "stage": stage,
                }
            },
        )

    async def _solve_submit_math_captcha(self, captcha_selector: str) -> str | None:
        started_at = asyncio.get_running_loop().time()
        track_captcha_attempt("math", phase="submit")
        hints = await self._extract_submit_captcha_hints(captcha_selector)
        if not hints:
            track_captcha_failure(
                "math_hint_not_found",
                phase="submit",
                strategy="math",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
            )
            return None

        min_confidence = self._captcha_math_min_confidence()
        for hint in hints:
            decision = captcha_engine.solve_text_with_confidence(hint)
            if not decision.value:
                continue
            if decision.confidence < min_confidence:
                logger.info(
                    "submit_math_captcha_low_confidence",
                    extra={"extra_fields": {"confidence": decision.confidence, "strategy": decision.strategy}},
                )
                continue

            solved = self._normalize_captcha_solution(decision.value)
            if solved:
                elapsed = asyncio.get_running_loop().time() - started_at
                track_captcha_success(
                    "math",
                    phase="submit",
                    confidence=decision.confidence,
                    latency_seconds=elapsed,
                )
                logger.info(
                    "submit_math_captcha_solved",
                    extra={"extra_fields": {"confidence": decision.confidence, "strategy": decision.strategy}},
                )
                return solved
        track_captcha_failure(
            "math_parse_failed",
            phase="submit",
            strategy="math",
            latency_seconds=asyncio.get_running_loop().time() - started_at,
        )
        return None

    async def _solve_submit_captcha_with_provider(self, captcha_selector: str) -> str | None:
        started_at = asyncio.get_running_loop().time()
        track_captcha_attempt("provider", phase="submit")
        provider = get_captcha_provider()
        if not provider:
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_submit_math_captcha(captcha_selector)
            track_captcha_failure(
                "provider_not_configured",
                phase="submit",
                strategy="provider",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
            )
            return None

        image_base64 = await self._extract_captcha_image_base64(captcha_selector)
        if not image_base64:
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_submit_math_captcha(captcha_selector)
            track_captcha_failure(
                "provider_image_not_found",
                phase="submit",
                strategy="provider",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
            )
            return None

        self._save_captcha_debug_artifact(
            image_base64, phase="submit", attempt=1, stage="captured", provider="composite"
        )
        try:
            result = await provider.solve_text_captcha(image_base64)
        except Exception as exc:
            self._save_captcha_debug_artifact(
                image_base64, phase="submit", attempt=1, stage="error", provider="composite", error=str(exc)
            )
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_submit_math_captcha(captcha_selector)
            track_captcha_failure(
                "provider_exception",
                phase="submit",
                strategy="provider",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
            )
            return None

        if not result.solved:
            self._save_captcha_debug_artifact(
                image_base64,
                phase="submit",
                attempt=1,
                stage="failed",
                provider=result.provider or "composite",
                error=result.error or "unsolved",
            )
            if utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED:
                return await self._solve_submit_math_captcha(captcha_selector)
            track_captcha_failure(
                result.error or "provider_invalid_value",
                phase="submit",
                strategy="provider",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
            )
            return None

        normalized = self._normalize_captcha_solution(result.value)
        if normalized:
            track_captcha_success(
                "provider",
                phase="submit",
                latency_seconds=asyncio.get_running_loop().time() - started_at,
            )
            logger.info(
                "submit_provider_captcha_solved",
                extra={"extra_fields": {"provider": result.provider}},
            )
            self._save_captcha_debug_artifact(
                image_base64,
                phase="submit",
                attempt=1,
                stage="solved",
                provider=result.provider or "composite",
                solution=normalized,
            )
            return normalized

        self._save_captcha_debug_artifact(
            image_base64,
            phase="submit",
            attempt=1,
            stage="failed",
            provider=result.provider or "composite",
            error="normalization_failed",
        )
        track_captcha_failure(
            "provider_invalid_value",
            phase="submit",
            strategy="provider",
            latency_seconds=asyncio.get_running_loop().time() - started_at,
        )
        return None

    async def _refresh_submit_captcha(self) -> bool:
        previous_fingerprint = await self._captcha_image_fingerprint()
        for selector in AuthSelectors.CAPTCHA_REFRESH_SELECTORS:
            try:
                btn = await self.smart_locator.locate(self.page, [selector], timeout=900)
                await btn.click()
                await self._wait_for_submit_captcha_refresh(previous_fingerprint)
                return True
            except Exception:
                continue

        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                img = await self.smart_locator.locate(self.page, [selector], timeout=900)
                await img.click()
                await self._wait_for_submit_captcha_refresh(previous_fingerprint)
                return True
            except Exception:
                continue
        return False

    async def _captcha_image_fingerprint(self) -> str:
        for selector in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
            try:
                value = await self.page.eval_on_selector(
                    selector,
                    """el => {
                        if (!el) return '';
                        const src = el.getAttribute('src') || '';
                        const data = el.getAttribute('data-src') || '';
                        const ts = el.getAttribute('data-timestamp') || '';
                        return `${src}|${data}|${ts}`;
                    }""",
                )
                cleaned = await self._as_clean_text(value)
                if cleaned:
                    return cleaned
            except Exception:
                continue
        return ""

    async def _wait_for_submit_captcha_refresh(self, previous_fingerprint: str) -> None:
        timeout_seconds = max(0.2, utcms_config.CAPTCHA_REFRESH_WAIT_SECONDS)
        deadline = asyncio.get_running_loop().time() + timeout_seconds
        while asyncio.get_running_loop().time() < deadline:
            current = await self._captcha_image_fingerprint()
            if current and current != previous_fingerprint:
                return
            await asyncio.sleep(0.05)
        await asyncio.sleep(timeout_seconds)

    async def _auto_fill_submit_captcha(self, captcha_selector: str) -> bool:
        attempts = max(1, utcms_config.CAPTCHA_AUTO_MAX_ATTEMPTS)
        retry_delay = max(0.1, utcms_config.CAPTCHA_AUTO_RETRY_DELAY_SECONDS)
        mode = (utcms_config.CAPTCHA_MODE or "").strip().lower()
        allow_provider = mode in ("provider_first", "provider_only")
        allow_math_fallback = mode != "provider_only" or utcms_config.CAPTCHA_LOCAL_FALLBACK_ENABLED

        for attempt in range(1, attempts + 1):
            if attempt > 1 and utcms_config.CAPTCHA_AUTO_REFRESH_ON_RETRY:
                await self._refresh_submit_captcha()
                await asyncio.sleep(retry_delay)

            if allow_provider:
                solved_provider = await self._solve_submit_captcha_with_provider(captcha_selector)
                if solved_provider and await self._fill_with_selector(captcha_selector, solved_provider):
                    return True

            if allow_math_fallback:
                solved_math = await self._solve_submit_math_captcha(captcha_selector)
                if solved_math and await self._fill_with_selector(captcha_selector, solved_math):
                    return True

        return False

    async def _handle_submit_captcha_if_present(self) -> None:
        captcha_selectors = (
            "input[name='DNTCaptchaInputText']",
            "input[id='DNTCaptchaInputText']",
            "input[name*='captcha' i][type='text']",
            "input[id*='captcha' i][type='text']",
        )

        combined_selector = ", ".join(captcha_selectors)
        captcha_selector = None
        try:
            locator = self.page.locator(combined_selector).first
            await locator.wait_for(state="visible", timeout=6000)
            for selector in captcha_selectors:
                if await self.page.locator(selector).first.is_visible():
                    captcha_selector = selector
                    break
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        if not captcha_selector:
            logger.info("No captcha input found on submit stage, skipping captcha solving.")
            return

        try:
            for img_sel in AuthSelectors.CAPTCHA_IMAGE_SELECTORS:
                img_loc = self.page.locator(img_sel).first
                if await img_loc.is_visible(timeout=500):
                    for _ in range(25):
                        width = await img_loc.evaluate("el => el.naturalWidth")
                        if width and width > 0:
                            break
                        await asyncio.sleep(0.05)
                    break
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        if utcms_config.UTCMS_CAPTCHA_VALUE:
            filled = await self._fill_with_selector(captcha_selector, utcms_config.UTCMS_CAPTCHA_VALUE)
            if filled:
                return
            raise WaybillError("فیلد کپچا یافت شد اما مقداردهی کپچا انجام نشد")

        solved_auto = await self._auto_fill_submit_captcha(captcha_selector)
        if solved_auto:
            return

        if utcms_config.CAPTCHA_AUTO_ONLY or (utcms_config.CAPTCHA_MODE or "").strip().lower() != "manual_only":
            logger.warning(
                "submit_captcha_auto_solve_failed", extra={"extra_fields": {"mode": utcms_config.CAPTCHA_MODE}}
            )
            track_captcha_failure("auto_solve_failed", phase="submit", strategy="auto")
            raise WaybillError(
                "حل خودکار کپچای ثبت نهایی ناموفق بود. " "فایل مدل CNN یا کیفیت تصویر کپچا را بررسی کنید."
            )

        if utcms_config.HEADLESS:
            raise WaybillError("کپچا برای ثبت نهایی لازم است. در حالت HEADLESS مقدار UTCMS_CAPTCHA_VALUE تنظیم شود.")

        timeout_seconds = max(5, utcms_config.UTCMS_MANUAL_CAPTCHA_TIMEOUT_SECONDS)
        poll_seconds = max(0.2, utcms_config.UTCMS_MANUAL_CAPTCHA_POLL_SECONDS)
        deadline = asyncio.get_running_loop().time() + timeout_seconds

        while asyncio.get_running_loop().time() < deadline:
            try:
                value = await self.page.eval_on_selector(
                    captcha_selector,
                    "el => (el.value || '').trim()",
                )
                if value:
                    return
            except Exception:
                logger.warning("waybill_enhanced_silent_error", exc_info=True)
            await asyncio.sleep(poll_seconds)

        raise WaybillError("کپچا در بازه زمانی مجاز تکمیل نشد")

    async def _fill_with_selector(self, selector: str, value: str) -> bool:
        try:
            locator = await self.smart_locator.locate(self.page, [selector], timeout=3500)
            await locator.fill(value)
            return True
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        if await self.interactor.safe_fill(selector, value):
            return True
        return await self._set_value_with_js(selector, value)

    async def _is_submission_successful(self) -> bool:
        """بررسی نشانه‌های موفقیت پس از ثبت."""
        # ابتدا بررسی خطاهای صریح - اگر خطا وجود دارد، موفق نیست
        error_selectors = [
            ".alert-danger",
            ".text-danger",
            ".validation-summary-errors",
            ".toast-error",
            ".swal2-html-container",
        ]
        for selector in error_selectors:
            try:
                texts = await self.page.eval_on_selector_all(
                    selector,
                    "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)",
                )
                for text in texts:
                    cleaned = await self._as_clean_text(text)
                    if cleaned:
                        for err_key in self._UTCMS_ERROR_MAP:
                            if err_key in cleaned.lower():
                                return False
            except Exception:
                continue

        success_selectors = [
            ".alert-success",
            ".toast-success",
            ".success-message",
            "text=با موفقیت ثبت شد",
            "text=بارنامه ثبت شد",
            "text=شماره بارنامه",
            "text=کد رهگیری",
            "text=چاپ بارنامه",
        ]
        for selector in success_selectors:
            try:
                if await self._is_selector_visible(selector):
                    return True
            except Exception:
                continue

        current_url = (await self._current_url()).lower()
        success_fragments = (
            "/print",
            "/details",
            "/success",
            "/notification",
            "/receipt",
            "/result",
        )
        if any(fragment in current_url for fragment in success_fragments):
            return True

        # بررسی عناصر موفقیت خاص بارنامه در صفحه
        try:
            body_text = await self._as_clean_text(await self.page.text_content("body"))
            body_text = self._to_english_digits(body_text)
            waybill_success_patterns = [
                "شماره بارنامه",
                "کد رهگیری",
                "با موفقیت ثبت شد",
                "بارنامه ثبت شد",
                "چاپ بارنامه",
            ]
            for pattern in waybill_success_patterns:
                if pattern in body_text:
                    return True
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        return False

    # نگاشت کدهای خطای UTCMS به پیام فارسی
    _UTCMS_ERROR_MAP = {
        "err_incorrect_password": "رمز عبور اشتباه است",
        "err_4001_faghed_parvane": "فاقد پروانه حمل‌ونقل معتبر",
        "err_permision1": "خطای مجوز (سطح ۱)",
        "err_permision2": "خطای مجوز (سطح ۲)",
        "err_not_same_province": "استان مبدا و مقصد باید یکسان باشد",
        "err_driver": "خطا در اطلاعات راننده",
        "err_driver2": "خطا در اطلاعات راننده (ثانویه)",
        "err_parvane_3": "خطای پروانه (نوع ۳)",
        "err_parvane2": "خطای پروانه (نوع ۲)",
        "err_realtion": "خطای ارتباط",
        "err_relation2": "خطای ارتباط (ثانویه)",
        "err_arrived_target": "سفر قبلی هنوز به مقصد نرسیده",
        "err_blocked": "حساب مسدود شده است",
        "err_suspend": "حساب معلق شده است",
        "err_raod_active": "مسیر فعال دیگری وجود دارد",
        "err_owner_shipping": "خطای مالک حمل‌ونقل",
        "err_wrong_otp": "کد OTP اشتباه است",
        "err_otp_required": "کد OTP مورد نیاز است",
        "err_barname_app": "خطای اپلیکیشن برنامه",
        "err_province_parvane": "خطای استان پروانه",
        "err_province_parvane_barname": "عدم تطابق استان پروانه با برنامه",
        "err_many_barname": "تعداد بارنامه‌های ثبت‌شده بیش از حد مجاز",
        "err_most_shipping": "تعداد حمل‌ها بیش از حد مجاز",
        "err_cant_shipping": "امکان ثبت حمل وجود ندارد",
    }

    async def _extract_form_errors(self) -> str | None:
        """استخراج خطاهای اعتبارسنجی فرم (شامل کدهای خطای UTCMS)."""
        error_selectors = [
            ".validation-summary-errors li",
            ".validation-summary-errors",
            ".field-validation-error",
            ".alert-danger",
            ".text-danger",
            ".toast-error",
            ".swal2-html-container",
            ".modal-body .alert",
            "[class*='error-message']",
        ]
        for selector in error_selectors:
            try:
                texts = await self.page.eval_on_selector_all(
                    selector,
                    "els => els.map(el => (el.textContent || '').trim()).filter(Boolean)",
                )
                for text in texts:
                    cleaned = await self._as_clean_text(text)
                    if cleaned:
                        for err_key, err_msg in self._UTCMS_ERROR_MAP.items():
                            if err_key in cleaned.lower():
                                return f"{err_msg} ({cleaned})"
                        return cleaned
            except Exception:
                continue

        # بررسی متن کامل صفحه برای کدهای خطای شناخته‌شده
        try:
            body_text = await self._as_clean_text(await self.page.text_content("body"))
            for err_key, err_msg in self._UTCMS_ERROR_MAP.items():
                if err_key in body_text.lower():
                    return err_msg
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        return None

    async def _extract_tracking_code(self, document_id: Any | None = None) -> str | None:
        """استخراج کد رهگیری از صفحه - فقط اعدادی که در بافت کد رهگیری/شماره بارنامه هستند"""
        import re

        fetched_code = await self._fetch_tracking_code_by_document_id(document_id)
        if fetched_code:
            return fetched_code

        # تلاش با انتخابگرهای مختص کد رهگیری
        selectors = [
            ".tracking-code",
            "#TrackingCode",
            "[data-tracking]",
            ".waybill-number",
            "#printId",
            "input[name='printId']",
        ]

        for selector in selectors:
            try:
                element = await self.page.query_selector(selector)
                if element is None:
                    element = await self.smart_locator.locate(self.page, [selector], timeout=900)
                text = await self._as_clean_text(await element.text_content())
                text = self._to_english_digits(text)
                # فقط اعدادی که در بافت کد رهگیری یا شماره بارنامه هستند
                labeled = re.findall(
                    r"(?:کد\s*رهگیری|شماره\s*بارنامه|tracking|waybill)\D*(\d{6,})", text, re.IGNORECASE
                )
                if labeled:
                    return labeled[0]
                # اگر المنت حاوی برچسب نیست، ولی خودش مختص کد رهگیری است، اولین عدد 6+ رقمی را برگردان
                codes = re.findall(r"\d{6,}", text or "")
                if codes:
                    return codes[0]
            except Exception:
                continue

        try:
            raw_body_text = await self.page.text_content("body")
            if isinstance(raw_body_text, str):
                body_text = await self._as_clean_text(raw_body_text)
                body_text = self._to_english_digits(body_text)
                labeled = re.findall(r"(?:کد\s*رهگیری|شماره\s*بارنامه)\D*(\d{6,})", body_text)
                if labeled:
                    return labeled[0]
        except Exception:
            logger.warning("waybill_enhanced_silent_error", exc_info=True)

        # تلاش با استفاده از URL (فقط اعداد با برچسب رهگیری در URL)
        url = await self._current_url()
        if "track" in url.lower() or "waybill" in url.lower() or "print" in url.lower() or "receipt" in url.lower():
            codes = re.findall(r"[A-Z0-9]{8,}", self._to_english_digits(url))
            if codes:
                return codes[0]

        return None
