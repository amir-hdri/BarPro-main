"""
انتخابگر مکان با قابلیت جایگزینی: نقشه ← منوی کشویی ← ورودی متنی
"""

import asyncio
import logging
from typing import Any

from playwright.async_api import Page

from app.automation.map_controller import GeoCoordinate, MapController
from app.automation.selectors import LocationSelectors
from app.core.exceptions import LocationSelectionError
from app.core.logging import monitoring_extra

logger = logging.getLogger(__name__)


class LocationSelector:
    """
    انتخابگر هوشمند مکان که روش‌های مختلف را امتحان می‌کند:
    ۱. انتخاب مبتنی بر نقشه
    ۲. انتخاب آبشاری (استان ← شهر ← منطقه)
    ۳. ورودی متنی با تکمیل خودکار
    """

    def __init__(self, page: Page):
        self.page = page
        self.map_controller = MapController(page)

    @staticmethod
    def _normalize_text(value: str | None) -> str:
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
    def _unique_preserve_order(items: list[str]) -> list[str]:
        seen = set()
        output: list[str] = []
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            output.append(item)
        return output

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

    def _additional_prefix_aliases(self, prefix: str) -> list[str]:
        """نگاشت prefix به alias های واقعی در فرم UTCMS"""
        lowered = (prefix or "").lower()
        if lowered == "origin":
            # UTCMS از Source استفاده می‌کند (ddStateSource, ddCitySource, ...)
            return ["Source", "Src", "source"]
        if lowered == "destination":
            # UTCMS از Dest استفاده می‌کند (ddStateDest, ddCityDest, ...)
            return ["Dest", "destination"]
        return []

    @staticmethod
    def _get_utcms_selectors(is_origin: bool) -> dict[str, list[str]]:
        """بازگشت انتخابگرهای مستقیم UTCMS برای مبدا یا مقصد"""
        from app.automation.selectors import LocationSelectors
        if is_origin:
            return LocationSelectors.UTCMS_ORIGIN_SELECTORS
        return LocationSelectors.UTCMS_DESTINATION_SELECTORS

    def _build_formatted_selectors(
        self,
        templates: list[str],
        prefix: str,
        extra_aliases: list[str] | None = None,
    ) -> list[str]:
        aliases = [prefix]
        aliases.extend(self._additional_prefix_aliases(prefix))
        if extra_aliases:
            aliases.extend(extra_aliases)

        selectors: list[str] = []
        for alias in self._unique_preserve_order(aliases):
            prefix_lower = alias.lower()
            for template in templates:
                # اگر template هیچ placeholder ای ندارد، یک بار اضافه می‌کنیم (absolute selector)
                if "{prefix}" not in template and "{prefix_lower}" not in template:
                    if template not in selectors:
                        selectors.append(template)
                    continue
                try:
                    selectors.append(template.format(prefix=alias, prefix_lower=prefix_lower))
                except (KeyError, ValueError):
                    continue

        return self._unique_preserve_order(selectors)

    async def _fill_input_like(self, selector: str, value: str, visible: bool = True) -> bool:
        if not value:
            return False

        target_selector = self._make_visible_selector(selector) if visible else selector
        
        # 1. Try native prototype setter bypass first (React/Vue/jQuery robust handling)
        try:
            updated = await self.page.eval_on_selector(
                target_selector,
                """(el, rawValue) => {
                    const value = String(rawValue ?? '');
                    if (!el) return false;

                    let prototype = Object.getPrototypeOf(el);
                    let setter = null;
                    while (prototype) {
                        const desc = Object.getOwnPropertyDescriptor(prototype, 'value');
                        if (desc && desc.set) {
                            setter = desc.set;
                            break;
                        }
                        prototype = Object.getPrototypeOf(prototype);
                    }

                    if (setter) {
                        setter.call(el, value);
                    } else {
                        el.value = value;
                    }
                    if (el._valueTracker) {
                        el._valueTracker.setValue(value);
                    }
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    el.dispatchEvent(new Event('keyup', { bubbles: true }));
                    if (window.jQuery) {
                        window.jQuery(el).trigger('input').trigger('change').trigger('keyup');
                    }
                    return true;
                }""",
                value,
            )
            if updated:
                return True
        except Exception:
            pass

        # 2. Fallback to Playwright's standard fill
        try:
            await self.page.fill(target_selector, value)
            await self.page.eval_on_selector(
                target_selector,
                "el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change').trigger('keyup'); } }",
            )
            return True
        except Exception:
            pass

        # 3. Fallback to locator fill
        try:
            locator = self.page.locator(target_selector).first
            if await locator.count() == 0:
                return False
            await locator.fill(value)
            await locator.evaluate(
                "el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change').trigger('keyup'); } }"
            )
            return True
        except Exception:
            pass

        return False

    async def _scroll_into_view(self, selector: str) -> bool:
        try:
            visible_selector = self._make_visible_selector(selector)
            await self.page.eval_on_selector(
                visible_selector,
                """el => {
                    if (!el) return false;
                    el.scrollIntoView({ block: 'center', inline: 'center', behavior: 'instant' });
                    return true;
                }""",
            )
            await asyncio.sleep(0.1)
            return True
        except Exception:
            return False

    async def _is_selector_visible(self, selector: str) -> bool:
        try:
            visible_selector = self._make_visible_selector(selector)
            return bool(await self.page.is_visible(visible_selector))
        except Exception:
            return False

    async def _ensure_location_tab_active(self, prefix: str) -> None:
        """فعال کردن tab مرحله مبدا یا مقصد"""
        # Map prefix/alias to tab numbers
        origin_prefixes = {"origin", "Origin", "source", "Source", "src", "Src"}
        dest_prefixes = {"destination", "Destination", "dest", "Dest"}

        if prefix in origin_prefixes:
            tab_id = "pills-5-tab"
            pane_id = "pills-5"
        elif prefix in dest_prefixes:
            tab_id = "pills-6-tab"
            pane_id = "pills-6"
        else:
            return

        tab_selector = f"#{tab_id}"
        pane_selector = f"#{pane_id}"

        try:
            is_visible = await self.page.eval_on_selector(
                pane_selector,
                """el => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    return !el.classList.contains('hidden')
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && el.classList.contains('active');
                }""",
            )
            if is_visible:
                return
        except Exception:
            pass

        # Try clicking the tab
        try:
            await self.page.click(tab_selector, timeout=3000)
            await asyncio.sleep(0.5)
        except Exception:
            pass

        # Force activate via JS if click didn't work
        try:
            await self.page.evaluate(
                """(tabId, paneId) => {
                    const tab = document.getElementById(tabId);
                    const pane = document.getElementById(paneId);
                    if (!tab || !pane) return;
                    document.querySelectorAll('[id^="pills-"][role="tab"]').forEach(t => {
                        t.classList.remove('active');
                        t.setAttribute('aria-selected', 'false');
                    });
                    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active', 'show'));
                    tab.classList.add('active');
                    tab.setAttribute('aria-selected', 'true');
                    pane.classList.add('active', 'show');
                    pane.scrollIntoView({ block: 'start', behavior: 'instant' });
                }""",
                tab_id,
                pane_id,
            )
            await asyncio.sleep(0.3)
        except Exception:
            pass

    async def _read_select_options(self, selector: str) -> list[dict[str, str]]:
        try:
            visible_selector = self._make_visible_selector(selector)
            option_parts = [f"{part.strip()} option" for part in visible_selector.split(",") if part.strip()]
            option_selector = ", ".join(option_parts)
            options = await self.page.eval_on_selector_all(
                option_selector,
                "els => els.map(el => ({text: (el.textContent || '').trim(), value: (el.getAttribute('value') || '').trim()}))",
            )
        except Exception:
            return []

        if not isinstance(options, list):
            return []
        return [
            {
                "text": str(option.get("text") or "").strip(),
                "value": str(option.get("value") or "").strip(),
            }
            for option in options
            if isinstance(option, dict)
        ]

    async def _wait_for_select_options(
        self,
        selectors: list[str],
        *,
        min_real_options: int = 1,
        timeout_ms: int = 12000,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                options = await self._read_select_options(selector)
                real_options = [
                    option
                    for option in options
                    if self._normalize_text(option.get("text", ""))
                    not in {"", "انتخابکنید...", "انتخابکنید", "undefined"}
                    and self._normalize_text(option.get("value", "")) not in {"", "0", "undefined"}
                ]
                if len(real_options) >= min_real_options:
                    return True
            await asyncio.sleep(0.25)
        return False

    async def _log_select_diagnostics(self, selector: str, field_label: str, target_value: str) -> None:
        try:
            options = await self._read_select_options(selector)
            logger.info(
                "location_select_diagnostics",
                extra={
                    "extra_fields": {
                        "selector": selector,
                        "field": field_label,
                        "target": target_value,
                        "options": options[:25],
                    }
                },
            )
        except Exception as exc:
            logger.warning(
                "location_select_diagnostics_failed",
                extra={
                    "extra_fields": {
                        "selector": selector,
                        "field": field_label,
                        "target": target_value,
                        "error": str(exc),
                    }
                },
            )

    async def _inspect_select_runtime(self, selector: str) -> dict[str, Any]:
        options = await self._read_select_options(selector)
        placeholder_count = 0
        undefined_count = 0
        real_options: list[dict[str, str]] = []

        for option in options:
            normalized_text = self._normalize_text(option.get("text", ""))
            normalized_value = self._normalize_text(option.get("value", ""))
            if normalized_text in {"", "انتخاب", "انتخابکنید", "انتخابکنید..."} or normalized_value in {"", "0"}:
                placeholder_count += 1
                continue
            if normalized_text == "undefined" or normalized_value == "undefined":
                undefined_count += 1
                continue
            real_options.append(option)

        visible = await self._is_selector_visible(selector)
        return {
            "selector": selector,
            "visible": visible,
            "total_options": len(options),
            "placeholder_count": placeholder_count,
            "undefined_count": undefined_count,
            "real_option_count": len(real_options),
            "real_option_samples": real_options[:5],
        }

    async def _assess_dropdown_runtime(
        self,
        selectors: dict[str, list[str]],
        prefix: str,
    ) -> dict[str, Any]:
        province_runtime: list[dict[str, Any]] = []
        for selector in selectors.get("province", [])[:3]:
            province_runtime.append(await self._inspect_select_runtime(selector))

        viable = any(item.get("real_option_count", 0) > 0 for item in province_runtime)
        undefined_only = bool(province_runtime) and all(
            item.get("visible") and item.get("real_option_count", 0) == 0 and item.get("undefined_count", 0) > 0
            for item in province_runtime
        )
        decision = "try_dropdown" if viable else "skip_dropdown"
        if undefined_only:
            decision = "skip_to_favorite_or_select2"

        runtime = {
            "prefix": prefix,
            "viable": viable,
            "undefined_only": undefined_only,
            "decision": decision,
            "province_runtime": province_runtime,
        }
        logger.info(
            "location_dropdown_runtime",
            extra=monitoring_extra(
                "location_dropdown_runtime",
                category="location_selection",
                payload=runtime,
                tags={"prefix": prefix},
                **runtime,
            ),
        )
        return runtime

    async def select_location(self, location_data: dict[str, Any], origin: bool = True) -> dict[str, Any]:
        """
        انتخاب مکان با استفاده از بهترین روش موجود

        اولویت:
        ۱. Fast-path UTCMS (انتخابگرهای مستقیم)
        ۲. جستجوی نقشه داخلی (Select2)
        ۳. آدرس مورد علاقه (favorite)
        ۴. مختصات صریح، نقشه
        ۵. منوی کشویی آبشاری
        ۶. ورودی متنی
        """
        prefix = "Origin" if origin else "Destination"
        logger.info(
            "location_selection_started",
            extra={"extra_fields": {"prefix": prefix, "location_data": location_data}},
        )

        # Ensure the correct pill is visible before doing anything
        await self._ensure_location_tab_active(prefix)
        await asyncio.sleep(0.3)

        coordinates = location_data.get("coordinates")

        # ── ۱. Fast-path: UTCMS direct dropdown fill ────────────────────
        utcms_result = await self._try_utcms_direct_fill(location_data, prefix)
        if utcms_result["success"]:
            logger.info("utcms_direct_fill_succeeded", extra={"extra_fields": {"prefix": prefix}})
            return utcms_result
        logger.warning(
            "utcms_direct_fill_failed_falling_back",
            extra={"extra_fields": {"prefix": prefix, "error": utcms_result.get("error")}},
        )

        selectors = {
            "province": self._build_formatted_selectors(
                LocationSelectors.PROVINCE_TEMPLATES,
                prefix=prefix,
            ),
            "city": self._build_formatted_selectors(
                LocationSelectors.CITY_TEMPLATES,
                prefix=prefix,
            ),
            "district": self._build_formatted_selectors(
                LocationSelectors.DISTRICT_TEMPLATES,
                prefix=prefix,
            ),
        }
        dropdown_runtime = await self._assess_dropdown_runtime(selectors, prefix)

        dropdown_result = {
            "success": False,
            "method": "dropdown",
            "error": "skipped_by_runtime",
            "runtime": dropdown_runtime,
        }

        # ── ۲. آدرس مورد علاقه ─────────────────────────────────────
        favorite_result = await self._try_favorite_address_selection(location_data, prefix)
        if favorite_result["success"]:
            return favorite_result
        logger.warning(
            "favorite_address_selection_failed_falling_back",
            extra={"extra_fields": {"prefix": prefix, "error": favorite_result.get("error")}},
        )

        # ── ۳. جستجوی ماپ داخلی ─────────────────────────────────────
        map_search_result = {"success": False, "error": "Not attempted"}
        if not coordinates or coordinates.get("lat") is None or coordinates.get("lng") is None:
            map_search_result = await self._try_internal_map_search(location_data, prefix)
            if map_search_result["success"]:
                return map_search_result
            logger.warning(
                "internal_map_search_failed_falling_back",
                extra={"extra_fields": {"prefix": prefix, "error": map_search_result.get("error")}},
            )

        # ── ۴. منوی کشویی آبشاری ─────────────────────────────────────
        if not coordinates or coordinates.get("lat") is None or coordinates.get("lng") is None:
            if dropdown_runtime.get("viable"):
                dropdown_result = await self._try_dropdown_selection(location_data, prefix, selectors=selectors)
                if dropdown_result["success"]:
                    return dropdown_result
                logger.warning(
                    "dropdown_selection_failed_falling_back",
                    extra={
                        "extra_fields": {
                            "prefix": prefix,
                            "error": dropdown_result.get("error"),
                            "runtime": dropdown_runtime,
                        }
                    },
                )
            else:
                logger.info(
                    "dropdown_selection_skipped",
                    extra={"extra_fields": {"prefix": prefix, "runtime": dropdown_runtime}},
                )

        # ── ۵. Geocoding + مختصات صریح ──────────────────────────────────
        inferred_coordinates = None
        if not coordinates or coordinates.get("lat") is None or coordinates.get("lng") is None:
            inferred_coordinates = await self._geocode_address(location_data)
            if inferred_coordinates:
                coordinates = inferred_coordinates
                location_data = {**location_data, "coordinates": inferred_coordinates}
                logger.info(
                    "location_geocoded_for_fallback",
                    extra={"extra_fields": {"prefix": prefix, "location_data": location_data}},
                )

        explicit_coords_result = {"success": False, "error": "بدون مختصات"}
        if coordinates and coordinates.get("lat") is not None and coordinates.get("lng") is not None:
            explicit_coords_result = await self._try_explicit_coordinates(location_data, prefix)
            if explicit_coords_result["success"]:
                return explicit_coords_result
            logger.info(
                "explicit_coordinates_failed_falling_back",
                extra={"extra_fields": {"prefix": prefix, "error": explicit_coords_result.get("error")}},
            )

        # ── ۶. نقشه با کلیک ─────────────────────────────────────────
        map_result = {"success": False, "error": "بدون مختصات"}
        if coordinates and coordinates.get("lat") is not None and coordinates.get("lng") is not None:
            map_result = await self._try_map_selection(location_data, prefix, selectors=selectors)
            if map_result["success"]:
                if inferred_coordinates:
                    map_result["method"] = "map_geocoded"
                return map_result
            logger.warning(
                "map_selection_failed_falling_back",
                extra={"extra_fields": {"prefix": prefix, "error": map_result.get("error")}},
            )

        if (
            coordinates and coordinates.get("lat") is not None and coordinates.get("lng") is not None
        ) and not inferred_coordinates:
            if dropdown_runtime.get("viable"):
                dropdown_result = await self._try_dropdown_selection(location_data, prefix, selectors=selectors)
                if dropdown_result["success"]:
                    return dropdown_result
                logger.warning(
                    "dropdown_selection_failed_falling_back",
                    extra={
                        "extra_fields": {
                            "prefix": prefix,
                            "error": dropdown_result.get("error"),
                            "runtime": dropdown_runtime,
                        }
                    },
                )

        # ── ۷. ورودی متنی ─────────────────────────────────────────────
        text_result = await self._try_text_input(location_data, prefix)
        if text_result["success"]:
            return text_result

        raise LocationSelectionError(
            f"همه روش‌های انتخاب مکان ({prefix}) با شکست مواجه شدند. "
            f"UTCMS: {utcms_result.get('error')} | "
            f"Favorite: {favorite_result.get('error')} | "
            f"MapSearch: {map_search_result.get('error')} | "
            f"نقشه: {map_result.get('error')} | "
            f"Dropdown: {dropdown_result.get('error')} | "
            f"متن: {text_result.get('error')}"
        )

    async def _try_utcms_direct_fill(
        self,
        location_data: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        """
        Fast-path مخصوص UTCMS: به جای جستجوی دینامیک،
        مستقیماً با #ddStateSource / #ddCitySource / #txtAddressSource کار می‌کند
        """
        is_origin = prefix in {"Origin", "Source", "origin", "source"}
        utcms = self._get_utcms_selectors(is_origin)
        province = (location_data.get("province") or "").strip()
        city = (location_data.get("city") or "").strip()
        district = (location_data.get("district") or "").strip()
        address = (location_data.get("address") or "").strip()

        if not province and not city:
            return {"success": False, "method": "utcms_direct", "error": "استان یا شهر داده نشده است"}

        try:
            # ۱. صبر برای لود شدن گزینه‌های استان
            province_ready = await self._wait_for_select_options(
                utcms["province"],
                min_real_options=1,
                timeout_ms=12000,
            )
            if not province_ready:
                return {
                    "success": False,
                    "method": "utcms_direct",
                    "error": "گزینه‌های استان بارگذاری نشدند",
                }

            # Log current options for debugging
            for sel in utcms["province"][:2]:
                await self._log_select_diagnostics(sel, f"{prefix} province (utcms)", province)

            # ۲. انتخاب استان
            province_selected = await self._select_from_options(utcms["province"], province)
            if not province_selected:
                return {
                    "success": False,
                    "method": "utcms_direct",
                    "error": f"انتخاب استان '{province}' ناموفق بود",
                }

            # ۳. صبر برای cascade شهر (AJAX بعد از انتخاب استان)
            city_ready = await self._wait_for_select_options(
                utcms["city"],
                min_real_options=1,
                timeout_ms=15000,
            )
            if not city_ready:
                logger.warning(
                    "utcms_direct_city_options_not_ready",
                    extra={"extra_fields": {"prefix": prefix, "province": province}},
                )

            for sel in utcms["city"][:2]:
                await self._log_select_diagnostics(sel, f"{prefix} city (utcms)", city)

            # ۴. انتخاب شهر
            city_selected = await self._select_from_options(utcms["city"], city)
            if not city_selected:
                logger.warning(
                    "utcms_direct_city_selection_failed",
                    extra={"extra_fields": {"prefix": prefix, "city": city}},
                )
                # در صورت ناموفقی شهر، همچنان ادامه می‌دهیم و آدرس را پر می‌کنیم

            # ۵. انتخاب منطقه (اختیاری)
            if district:
                district_ready = await self._wait_for_select_options(
                    utcms["district"],
                    min_real_options=1,
                    timeout_ms=5000,
                )
                if district_ready:
                    await self._select_from_options(utcms["district"], district)

            # ۶. پر کردن آدرس
            if address:
                addr_filled = False
                for sel in utcms["address"]:
                    filled = await self._fill_input_like(sel, address)
                    if filled:
                        addr_filled = True
                        break
                if not addr_filled:
                    logger.warning(
                        "utcms_direct_address_fill_failed",
                        extra={"extra_fields": {"prefix": prefix, "selectors": utcms["address"]}},
                    )

            return {
                "success": True,
                "method": "utcms_direct",
                "province": province,
                "city": city,
                "district": district,
                "address": address,
            }

        except Exception as exc:
            return {"success": False, "method": "utcms_direct", "error": str(exc)}

    async def _fill_coordinate_hidden_fields(self, lat: float, lng: float, prefix: str) -> bool:
        """تلاش برای یافتن و پر کردن hidden fields مربوط به مختصات"""
        pane_id = "pills-5" if prefix == "Origin" else "pills-6"
        other_pane_id = "pills-6" if prefix == "Origin" else "pills-5"
        other_prefix_lower = "destination" if prefix == "Origin" else "origin"

        # Dynamically exclude inputs of the other prefix/pane to prevent cross-contamination
        if prefix == "Origin":
            exclusions = [
                f"#{other_pane_id} *",
                f'[name*="{other_prefix_lower}" i]',
                f'[id*="{other_prefix_lower}" i]',
                '[name*="dest" i]',
                '[id*="dest" i]',
                '[name*="magsad" i]',
                '[id*="magsad" i]',
            ]
        else:
            exclusions = [
                f"#{other_pane_id} *",
                f'[name*="{other_prefix_lower}" i]',
                f'[id*="{other_prefix_lower}" i]',
                '[name*="source" i]',
                '[id*="source" i]',
                '[name*="start" i]',
                '[id*="start" i]',
                '[name*="src" i]',
                '[id*="src" i]',
                '[name*="mabda" i]',
                '[id*="mabda" i]',
            ]
        not_clause = "".join(f":not({ex})" for ex in exclusions)

        lat_selectors = [
            f'input[name="{prefix}Lat"]',
            f'input[name="{prefix}Latitude"]',
            f'input[id="{prefix.lower()}_lat"]',
            f'input[id="{prefix.lower()}_latitude"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"][name*="lat"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"][name*="latitude"]',
            # Tab pane-scoped
            f'#{pane_id} input[name*="lat"]',
            f'#{pane_id} input[name*="lat" i]',
            f'#{pane_id} input[name*="latitude" i]',
            f'#{pane_id} input[id*="lat" i]',
            f'#{pane_id} input[id*="latitude" i]',
            # Page-wide fallbacks (constrained by exclusions)
            f'input[name*="lat" i]{not_clause}',
            f'input[name*="latitude" i]{not_clause}',
            f'input[id*="lat" i]{not_clause}',
            f'input[id*="latitude" i]{not_clause}',
            # Generic hidden coordinates (constrained by exclusions)
            f'input[type="hidden"][name*="lat" i]{not_clause}',
            f'input[type="hidden"][id*="lat" i]{not_clause}',
            f'input[type="hidden"][name*="latitude" i]{not_clause}',
            f'input[type="hidden"][id*="latitude" i]{not_clause}',
            f'input[type="hidden"][name="lat"]{not_clause}',
            f'input[type="hidden"][id="lat"]{not_clause}',
        ]

        lng_selectors = [
            f'input[name="{prefix}Lng"]',
            f'input[name="{prefix}Longitude"]',
            f'input[id="{prefix.lower()}_lng"]',
            f'input[id="{prefix.lower()}_longitude"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"][name*="lng"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"][name*="longitude"]',
            # Tab pane-scoped
            f'#{pane_id} input[name*="lng"]',
            f'#{pane_id} input[name*="lng" i]',
            f'#{pane_id} input[name*="longitude" i]',
            f'#{pane_id} input[id*="lng" i]',
            f'#{pane_id} input[id*="longitude" i]',
            f'#{pane_id} input[name*="lon" i]',
            f'#{pane_id} input[id*="lon" i]',
            # Page-wide fallbacks (constrained by exclusions)
            f'input[name*="lng" i]{not_clause}',
            f'input[name*="longitude" i]{not_clause}',
            f'input[id*="lng" i]{not_clause}',
            f'input[id*="longitude" i]{not_clause}',
            f'input[name*="lon" i]{not_clause}',
            f'input[id*="lon" i]{not_clause}',
            # Generic hidden coordinates (constrained by exclusions)
            f'input[type="hidden"][name*="lng" i]{not_clause}',
            f'input[type="hidden"][id*="lng" i]{not_clause}',
            f'input[type="hidden"][name*="longitude" i]{not_clause}',
            f'input[type="hidden"][id*="longitude" i]{not_clause}',
            f'input[type="hidden"][name*="lon" i]{not_clause}',
            f'input[type="hidden"][id*="lon" i]{not_clause}',
            f'input[type="hidden"][name="lng"]{not_clause}',
            f'input[type="hidden"][id="lng"]{not_clause}',
            f'input[type="hidden"][name="lon"]{not_clause}',
            f'input[type="hidden"][id="lon"]{not_clause}',
        ]

        lat_filled = False
        for selector in lat_selectors:
            if await self._fill_input_like(selector, str(lat), visible=False):
                lat_filled = True

        lng_filled = False
        for selector in lng_selectors:
            if await self._fill_input_like(selector, str(lng), visible=False):
                lng_filled = True

        return lat_filled and lng_filled

    async def _inject_coordinates_via_js(self, lat: float, lng: float, prefix: str) -> bool:
        """تلاش برای تزریق مستقیم مختصات به متغیرهای سراسری JS و inputهای مخفی"""
        injection_script = """
        ([lat, lng, prefix]) => {
            const prefixLower = prefix.toLowerCase();
            const isOrigin = prefixLower === "origin" || prefixLower === "source" || prefixLower === "src" || prefixLower === "mabda";
            
            let found = false;

            // 1. تزریق به متغیرهای سراسری پنجره مرورگر (فول‌استک و اختصاصی UTCMS)
            try {
                if (isOrigin) {
                    if (typeof LatSource !== 'undefined') { LatSource = lat; found = true; }
                    if (typeof LngSource !== 'undefined') { LngSource = lng; found = true; }
                    if (typeof PlaceSource !== 'undefined') {
                        PlaceSource.Lat = lat;
                        PlaceSource.Lon = lng;
                        found = true;
                    }
                    if (typeof window.LatSource !== 'undefined') { window.LatSource = lat; found = true; }
                    if (typeof window.LngSource !== 'undefined') { window.LngSource = lng; found = true; }
                } else {
                    if (typeof LatDestination !== 'undefined') { LatDestination = lat; found = true; }
                    if (typeof LngDestination !== 'undefined') { LngDestination = lng; found = true; }
                    if (typeof PlaceDestination !== 'undefined') {
                        PlaceDestination.Lat = lat;
                        PlaceDestination.Lon = lng;
                        found = true;
                    }
                    if (typeof window.LatDestination !== 'undefined') { window.LatDestination = lat; found = true; }
                    if (typeof window.LngDestination !== 'undefined') { window.LngDestination = lng; found = true; }
                }
            } catch (e) {
                console.error("Global JS coordinate injection failed:", e);
            }

            // 2. تزریق به inputهای مخفی و معمولی DOM
            const inputs = document.querySelectorAll('input');
            
            const setValue = (el, val) => {
                let setter = null;
                try {
                    // Try getting setter from HTMLInputElement prototype explicitly
                    setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                } catch(e) {}

                if (!setter) {
                    // Fallback to traversing prototype chain
                    let prototype = Object.getPrototypeOf(el);
                    while (prototype) {
                        const desc = Object.getOwnPropertyDescriptor(prototype, 'value');
                        if (desc && desc.set) {
                            setter = desc.set;
                            break;
                        }
                        prototype = Object.getPrototypeOf(prototype);
                    }
                }

                if (setter) {
                    setter.call(el, val);
                } else {
                    el.value = val;
                }
                if (el._valueTracker) {
                    el._valueTracker.setValue(val);
                }
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.dispatchEvent(new Event('keyup', { bubbles: true }));
                if (window.jQuery) {
                    window.jQuery(el).trigger('input').trigger('change').trigger('keyup');
                }
            };

            inputs.forEach(input => {
                const name = (input.name || '').toLowerCase();
                const id = (input.id || '').toLowerCase();

                const isLat = name.includes('lat') || id.includes('lat') || name.includes('latitude') || id.includes('latitude');
                const isLng = name.includes('lng') || id.includes('lng') || name.includes('lon') || id.includes('lon') || name.includes('longitude') || id.includes('longitude');

                if (!isLat && !isLng) return;

                let prefixMatch = false;
                if (isOrigin) {
                    if (name.includes('origin') || id.includes('origin') || name.includes('source') || id.includes('source') || name.includes('mabda') || id.includes('mabda') || name.includes('start') || id.includes('start')) {
                        prefixMatch = true;
                    } else if (!(name.includes('dest') || id.includes('dest') || name.includes('magsad') || id.includes('magsad'))) {
                        const insideOriginPane = input.closest('#pills-5');
                        const insideDestPane = input.closest('#pills-6');
                        if (insideOriginPane) {
                            prefixMatch = true;
                        } else if (!insideDestPane) {
                            prefixMatch = true;
                        }
                    }
                } else {
                    if (name.includes('dest') || id.includes('dest') || name.includes('magsad') || id.includes('magsad')) {
                        prefixMatch = true;
                    } else if (!(name.includes('origin') || id.includes('origin') || name.includes('source') || id.includes('source') || name.includes('mabda') || id.includes('mabda'))) {
                        const insideOriginPane = input.closest('#pills-5');
                        const insideDestPane = input.closest('#pills-6');
                        if (insideDestPane) {
                            prefixMatch = true;
                        } else if (!insideOriginPane) {
                            prefixMatch = true;
                        }
                    }
                }

                if (prefixMatch) {
                    if (isLat) {
                        setValue(input, lat);
                        found = true;
                    } else if (isLng) {
                        setValue(input, lng);
                        found = true;
                    }
                }
            });

            return found;
        }
        """
        injected = await self.page.evaluate(injection_script, [lat, lng, prefix])
        return bool(injected)

    async def _try_explicit_coordinates(self, location_data: dict[str, Any], prefix: str) -> dict[str, Any]:
        """تلاش برای استفاده مستقیم از مختصات با پر کردن متغیرهای سراسری و فراخوانی متدهای بومی نقشه"""
        coordinates = location_data.get("coordinates")
        if not coordinates:
            return {"success": False, "method": "explicit_coords", "error": "مختصات موجود نیست"}

        try:
            lat = coordinates.get("lat")
            lng = coordinates.get("lng")

            if lat is None or lng is None:
                return {"success": False, "method": "explicit_coords", "error": "مختصات ناقص"}

            province = location_data.get("province") or ""
            city = location_data.get("city") or ""
            address = location_data.get("address") or ""

            # 1. تزریق مستقیم به متغیرهای سراسری و اجرای متد بومی reverse mapping نقشه
            native_called = await self.page.evaluate(
                """([lat, lng, prefix, state, city, addr]) => {
                    const isOrigin = prefix === "Origin";
                    let called = false;
                    
                    try {
                        if (isOrigin) {
                            if (typeof LatSource !== 'undefined') LatSource = lat;
                            if (typeof LngSource !== 'undefined') LngSource = lng;
                            if (typeof PlaceSource !== 'undefined') {
                                PlaceSource.Lat = lat;
                                PlaceSource.Lon = lng;
                                PlaceSource.StateName = state;
                                PlaceSource.CityName = city;
                                PlaceSource.Address = addr;
                            }
                            if (typeof RevereseMapLatSource === 'function') {
                                RevereseMapLatSource(lat, lng);
                                called = true;
                            }
                        } else {
                            if (typeof LatDestination !== 'undefined') LatDestination = lat;
                            if (typeof LngDestination !== 'undefined') LngDestination = lng;
                            if (typeof PlaceDestination !== 'undefined') {
                                PlaceDestination.Lat = lat;
                                PlaceDestination.Lon = lng;
                                PlaceDestination.StateName = state;
                                PlaceDestination.CityName = city;
                                PlaceDestination.Address = addr;
                            }
                            if (typeof RevereseMapLatDest === 'function') {
                                RevereseMapLatDest(lat, lng);
                                called = true;
                            }
                        }
                    } catch(e) {
                        console.error("Native reverse mapping call failed:", e);
                    }
                    return called;
                }""",
                [lat, lng, prefix, province, city, address]
            )

            # 2. تزریق به فیلدهای مخفی DOM به عنوان پشتیبان
            await self._fill_coordinate_hidden_fields(lat, lng, prefix)
            await self._inject_coordinates_via_js(lat, lng, prefix)

            # 3. اگر متد بومی اجرا شد، منتظر پر شدن فیلدهای آدرس می‌شویم
            if native_called:
                addr_selector = "#txtAddressSource" if prefix == "Origin" else "#txtAddressDest"
                state_selector = "#ddStateSource" if prefix == "Origin" else "#ddStateDest"
                
                # حداکثر 3 ثانیه برای پاسخ دهی متد بومی صبر می‌کنیم
                for _ in range(15):
                    try:
                        addr_val = await self.page.locator(addr_selector).input_value()
                        state_val = await self.page.locator(state_selector).input_value()
                        if addr_val and state_val:
                            logger.info(f"Native reverse mapping successfully populated fields for {prefix}.")
                            return {
                                "success": True,
                                "method": "explicit_coordinates_native_reverse_mapped",
                                "coordinates": {"lat": lat, "lng": lng},
                            }
                    except Exception:
                        pass
                    await asyncio.sleep(0.2)

            # 4. اگر فیلدها پر نشدند (مثلا به خاطر خطای سرویس نقشه سایت)، به صورت دستی فیلدهای دراپ‌دان را پر می‌کنیم
            logger.warning(
                f"Native reverse mapping did not populate fields for {prefix}. Falling back to manual dropdown/input entry."
            )
            dropdown_result = await self._try_dropdown_selection(location_data, prefix)
            if dropdown_result["success"]:
                return {
                    "success": True,
                    "method": "explicit_coordinates_dropdown_fallback",
                    "coordinates": {"lat": lat, "lng": lng},
                }

            return {
                "success": False,
                "method": "explicit_coords",
                "error": "عدم موفقیت در مقداردهی بومی و دستی فیلدهای مکان",
            }
        except Exception as e:
            return {"success": False, "method": "explicit_coords", "error": str(e)}

    async def _get_form_state(self, selectors: dict[str, list[str]], prefix: str) -> dict[str, str]:
        """دریافت وضعیت فعلی فیلدهای فرم (استان، شهر، آدرس و مختصات پنهان)"""
        state = {}

        for field_name in ["province", "city", "district", "address"]:
            if field_name in selectors and selectors[field_name]:
                for selector in selectors[field_name]:
                    try:
                        visible_selector = self._make_visible_selector(selector)
                        element = await self.page.query_selector(visible_selector)
                        if element:
                            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
                            if tag_name in ["input", "textarea"]:
                                value = await element.input_value()
                            else:
                                value = await element.evaluate("""el => {
                                    if (el.selectedIndex >= 0) {
                                        const option = el.options[el.selectedIndex];
                                        return option.value ? option.text : '';
                                    }
                                    return '';
                                }""")

                            if value and value.strip():
                                state[field_name] = value.strip()
                                break
                    except Exception:
                        continue

        hidden_lat_selectors = [
            f'input[name="{prefix}Lat"]',
            f'input[name="{prefix}Latitude"]',
            f'input[id="{prefix.lower()}_lat"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"][name*="Lat"]',
        ]
        hidden_lng_selectors = [
            f'input[name="{prefix}Lng"]',
            f'input[name="{prefix}Longitude"]',
            f'input[id="{prefix.lower()}_lng"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"][name*="Lng"]',
        ]

        for selector in hidden_lat_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    value = await element.input_value()
                    if value and value.strip():
                        state["lat"] = value.strip()
                        break
            except Exception:
                continue

        for selector in hidden_lng_selectors:
            try:
                element = await self.page.query_selector(selector)
                if element:
                    value = await element.input_value()
                    if value and value.strip():
                        state["lng"] = value.strip()
                        break
            except Exception:
                continue

        return state

    async def _try_map_selection(
        self,
        location_data: dict[str, Any],
        prefix: str,
        selectors: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """تلاش برای انتخاب مکان با استفاده از نقشه و تزریق مختصات به متغیرهای بومی"""
        # اول پنل صحیح را فعال کنیم، سپس نقشه را تشخیص دهیم
        await self._ensure_location_tab_active(prefix)
        await asyncio.sleep(0.4)

        map_type = await self.map_controller.detect_map_type()
        if not map_type:
            return {"success": False, "method": "map", "error": "نقشه‌ای یافت نشد"}

        coordinates = location_data.get("coordinates")
        if not coordinates:
            return {"success": False, "method": "map", "error": "مختصات صریح کاربر ارسال نشده است"}

        lat = coordinates.get("lat")
        lng = coordinates.get("lng")
        if lat is None or lng is None:
            return {"success": False, "method": "map", "error": "مختصات ناقص است"}

        try:
            location = GeoCoordinate(
                latitude=lat,
                longitude=lng,
                address=location_data.get("address"),
            )

            is_origin = prefix in {"Origin", "Source", "origin", "source"}
            utcms = self._get_utcms_selectors(is_origin)
            before_state = await self._get_form_state(selectors, prefix) if selectors else {}

            map_selector = "#MapSource" if is_origin else "#MapDestination"
            selected = await self.map_controller.select_on_map(
                selector=map_selector,
                location=location,
                search_input_selector=None,
            )

            if not selected:
                return {
                    "success": False,
                    "method": "map",
                    "error": "انتخاب نقطه روی نقشه انجام نشد",
                }

            await self.map_controller.wait_for_map_idle()

            # تزریق مختصات به hidden fields به عنوان safety net
            await self._fill_coordinate_hidden_fields(lat, lng, prefix)
            await self._inject_coordinates_via_js(lat, lng, prefix)

            if selectors:
                # صبر برای دریافت پاسخ بومی معکوس نقشه و مقداردهی فیلدها (حداکثر ۳ ثانیه)
                has_changes = False
                after_state = {}
                for _ in range(15):
                    after_state = await self._get_form_state(selectors, prefix)
                    has_changes = any(
                        val and val != before_state.get(key)
                        for key, val in after_state.items()
                    )
                    if has_changes:
                        break
                    await asyncio.sleep(0.2)

                if not after_state:
                    # after_state خالی = فیلدها در DOM نیستند → موفق فرض می‌کنیم
                    logger.info(
                        "map_click_form_state_empty_assuming_success",
                        extra={"extra_fields": {"prefix": prefix}},
                    )
                else:
                    if not has_changes and after_state == before_state:
                        logger.warning(
                            "map_click_had_no_effect_on_form",
                            extra={"extra_fields": {"prefix": prefix}},
                        )
                        # Fallback: پر کردن فیلد آدرس متنی
                        address = location_data.get("address", "")
                        if address:
                            for sel in utcms["address"]:
                                if await self._fill_input_like(sel, address):
                                    break
                        return {
                            "success": False,
                            "method": "map",
                            "error": "کلیک روی نقشه تاثیری در فرم نداشت (فیلدها تغییر نکردند)",
                        }

            return {
                "success": True,
                "method": "map",
                "coordinates": {"lat": lat, "lng": lng},
                "map_type": map_type,
            }
        except Exception as e:
            return {"success": False, "method": "map", "error": str(e)}

    async def _try_dropdown_selection(
        self,
        location_data: dict[str, Any],
        prefix: str,
        *,
        selectors: dict[str, list[str]] | None = None,
    ) -> dict[str, Any]:
        """تلاش برای انتخاب آبشاری (استان ← شهر ← منطقه)"""
        try:
            await self._ensure_location_tab_active(prefix)

            is_origin = prefix in {"Origin", "Source", "origin", "source"}
            utcms = self._get_utcms_selectors(is_origin)

            # ساختن لیست انتخابگر با اولویت UTCMS direct selectors
            if selectors is None:
                province_tmpl = self._build_formatted_selectors(
                    LocationSelectors.PROVINCE_TEMPLATES, prefix=prefix
                )
                city_tmpl = self._build_formatted_selectors(
                    LocationSelectors.CITY_TEMPLATES, prefix=prefix
                )
                district_tmpl = self._build_formatted_selectors(
                    LocationSelectors.DISTRICT_TEMPLATES, prefix=prefix
                )
            else:
                province_tmpl = selectors["province"]
                city_tmpl = selectors["city"]
                district_tmpl = selectors.get("district", [])

            # Merge UTCMS direct selectors at the head (highest priority)
            merged_province = self._unique_preserve_order(utcms["province"] + province_tmpl)
            merged_city    = self._unique_preserve_order(utcms["city"]     + city_tmpl)
            merged_district = self._unique_preserve_order(utcms["district"] + district_tmpl)

            await self._wait_for_select_options(merged_province, timeout_ms=12000)
            for selector in merged_province[:3]:
                await self._log_select_diagnostics(
                    selector, f"{prefix} province", str(location_data.get("province", ""))
                )

            province_selected = await self._select_from_options(merged_province, location_data.get("province", ""))
            if not province_selected:
                return {"success": False, "method": "dropdown", "error": "انتخاب استان با شکست مواجه شد"}

            city_options_ready = await self._wait_for_select_options(merged_city, timeout_ms=15000)
            if not city_options_ready:
                logger.warning(
                    "location_city_options_not_ready",
                    extra={"extra_fields": {"prefix": prefix, "location_data": location_data}},
                )
            for selector in merged_city[:3]:
                await self._log_select_diagnostics(selector, f"{prefix} city", str(location_data.get("city", "")))

            city_selected = await self._select_from_options(merged_city, location_data.get("city", ""))
            if not city_selected:
                return {"success": False, "method": "dropdown", "error": "انتخاب شهر با شکست مواجه شد"}

            await self._wait_for_select_options(merged_district, timeout_ms=5000)
            await self._select_from_options(merged_district, location_data.get("district", ""))

            # پر کردن آدرس - ابتدا UTCMS direct, سپس template
            address_selectors = self._unique_preserve_order(
                utcms["address"]
                + self._build_formatted_selectors(LocationSelectors.ADDRESS_TEMPLATES, prefix=prefix)
            )
            address = location_data.get("address", "")
            if address:
                for selector in address_selectors:
                    try:
                        filled = await self._fill_input_like(selector, address)
                        if filled:
                            break
                    except Exception:
                        continue

            return {
                "success": True,
                "method": "dropdown",
                "province": location_data.get("province"),
                "city": location_data.get("city"),
                "district": location_data.get("district"),
            }
        except Exception as e:
            return {"success": False, "method": "dropdown", "error": str(e)}

    async def _try_favorite_address_selection(
        self,
        location_data: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        try:
            await self._ensure_location_tab_active(prefix)

            # ماپ همه alias های مبدا به grid/button مرتبط
            is_origin = prefix in {"Origin", "Source", "origin", "source"}
            grid_id = "gridfulSenderAddress" if is_origin else "gridfulReceiverAddress"
            button_selector_inner = "#selectSenderAddress" if is_origin else "#selectReceiverAddress"
            grid_selector = f"#{grid_id}"

            if not await self.page.query_selector(grid_selector):
                return {"success": False, "method": "favorite", "error": "grid یافت نشد"}

            target_province = self._normalize_text(str(location_data.get("province") or ""))
            target_city = self._normalize_text(str(location_data.get("city") or ""))
            target_address = self._normalize_text(str(location_data.get("address") or ""))
            rows = await self.page.eval_on_selector_all(
                f"{grid_selector} tbody tr",
                """rows => rows.map((row, index) => {
                    const cells = Array.from(row.querySelectorAll('td')).map(td => (td.innerText || td.textContent || '').trim());
                    return { index, cells };
                })""",
            )
            if not rows:
                return {"success": False, "method": "favorite", "error": "رکوردی در grid موجود نیست"}

            best_index = None
            best_score = -1
            for row in rows:
                cells = [self._normalize_text(cell) for cell in (row.get("cells") or [])]
                score = 0
                haystack = " ".join(cells)
                if target_province and target_province in haystack:
                    score += 2
                if target_city and target_city in haystack:
                    score += 3
                if target_address and any(part for part in target_address.split("،") if part and part in haystack):
                    score += 1
                if score > best_score:
                    best_score = score
                    best_index = int(row.get("index", -1))

            if best_index is None or best_score <= 0:
                return {"success": False, "method": "favorite", "error": "آدرس نزدیک یافت نشد"}

            row_selector = f"{grid_selector} tbody tr:nth-child({best_index + 1})"
            btn_selector = f"{row_selector} {button_selector_inner}"
            await self._scroll_into_view(btn_selector)
            try:
                await self.page.click(btn_selector, timeout=3000)
            except Exception:
                # تلاش با JS در صورت شکست click
                await self.page.eval_on_selector(btn_selector, "el => el && el.click()")
            await asyncio.sleep(0.8)
            return {"success": True, "method": "favorite", "row_index": best_index}
        except Exception as exc:
            return {"success": False, "method": "favorite", "error": str(exc)}

    async def _select2_pick(self, select_selector: str, search_value: str) -> bool:
        if not search_value:
            return False
        try:
            await self._scroll_into_view(select_selector)
            container_selector = f"span.select2:has(#{select_selector.lstrip('#')}) .select2-selection"
            try:
                await self.page.click(container_selector, timeout=2000)
            except Exception:
                await self.page.locator(
                    f"xpath=//select[@id='{select_selector.lstrip('#')}']/following-sibling::span[contains(@class,'select2')][1]//span[contains(@class,'select2-selection')]"
                ).click(timeout=2500)
            await asyncio.sleep(0.3)
            search_input = self.page.locator("input.select2-search__field").last
            await search_input.fill(search_value, timeout=3000)
            await asyncio.sleep(1.0)
            results = self.page.locator(".select2-results__option")
            count = await results.count()
            for idx in range(count):
                option = results.nth(idx)
                text = self._normalize_text(await option.inner_text())
                target = self._normalize_text(search_value)
                if target and (target in text or text in target):
                    await option.click(timeout=3000)
                    await asyncio.sleep(0.5)
                    try:
                        await self.page.eval_on_selector(
                            select_selector,
                            "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }",
                        )
                    except Exception:
                        pass
                    return True
            if count > 0:
                await results.nth(0).click(timeout=3000)
                await asyncio.sleep(0.5)
                try:
                    await self.page.eval_on_selector(
                        select_selector,
                        "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }",
                    )
                except Exception:
                    pass
                return True
        except Exception:
            return False
        return False

    async def _wait_for_non_empty_text(self, selectors: list[str], timeout_ms: int = 10000) -> str | None:
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                try:
                    value = await self.page.eval_on_selector(
                        selector,
                        """el => {
                            if (!el) return '';
                            if ('value' in el) return String(el.value || '').trim();
                            return String((el.innerText || el.textContent || '')).trim();
                        }""",
                    )
                    if value:
                        return str(value)
                except Exception:
                    continue
            await asyncio.sleep(0.25)
        return None

    async def _try_internal_map_search(self, location_data: dict[str, Any], prefix: str) -> dict[str, Any]:
        try:
            await self._ensure_location_tab_active(prefix)
            map_city_id = "MapCity" if prefix == "Origin" else "MapCity2"
            address_search_id = "AddressSearch" if prefix == "Origin" else "AddressSearch2"
            search_button_id = "btnsearchAddressSource" if prefix == "Origin" else "btnsearchAddressDest"
            # Fallback selectors for UTCMS site compatibility
            if prefix == "Destination":
                search_button_id = "btnsearchAddressDest"  # Primary
                try:
                    if not await self.page.query_selector(f"#{search_button_id}"):
                        search_button_id = "btnsearchAddressDes"  # UTCMS site variant
                except Exception:
                    search_button_id = "btnsearchAddressDes"  # Fallback to UTCMS variant
            readonly_address_id = "txtAddressSourceFromMap" if prefix == "Origin" else "txtAddressDestFromMap"

            map_city = f"#{map_city_id}"
            address_search = f"#{address_search_id}"
            search_button = f"#{search_button_id}"
            readonly_address = f"#{readonly_address_id}"

            city = str(location_data.get("city") or "").strip()
            address = str(location_data.get("address") or "").strip()

            picked_city = await self._select2_pick(map_city, city)
            picked_address = await self._select2_pick(address_search, address or city)
            if not picked_city and not picked_address:
                return {"success": False, "method": "map_search", "error": "select2 map fields انتخاب نشد"}

            await self._scroll_into_view(search_button)
            try:
                await self.page.click(search_button, timeout=2500)
            except Exception:
                await self.page.eval_on_selector(search_button, "el => el && el.click()")
            resolved_address = await self._wait_for_non_empty_text([readonly_address], timeout_ms=12000)
            if not resolved_address:
                return {"success": False, "method": "map_search", "error": "خروجی آدرس نقشه پر نشد"}

            return {
                "success": True,
                "method": "map_search",
                "address": resolved_address,
            }
        except Exception as exc:
            return {"success": False, "method": "map_search", "error": str(exc)}

    async def _try_text_input(self, location_data: dict[str, Any], prefix: str) -> dict[str, Any]:
        """تلاش برای ورودی متنی با تکمیل خودکار"""
        try:
            input_selectors = self._build_formatted_selectors(
                LocationSelectors.INPUT_TEMPLATES,
                prefix=prefix,
                extra_aliases=["2"],
            )

            search_text = f"{location_data.get('city', '')} {location_data.get('address', '')}".strip()
            city = (location_data.get("city") or "").strip()

            for selector in input_selectors:
                try:
                    if not search_text and not city:
                        break

                    filled = await self._fill_input_like(selector, search_text or city)
                    if not filled:
                        selected = await self._select_from_options([selector], city or search_text)
                        if not selected:
                            continue

                    await asyncio.sleep(0.5)
                    await asyncio.sleep(1)

                    suggestion_selectors = LocationSelectors.SUGGESTION_SELECTORS
                    for sugg_selector in suggestion_selectors:
                        sugg = await self.page.query_selector(sugg_selector)
                        if sugg:
                            await sugg.click()
                            return {"success": True, "method": "autocomplete", "search": search_text}
                except Exception:
                    continue

            return {"success": False, "method": "autocomplete", "error": "هیچ پیشنهادی یافت نشد"}
        except Exception as e:
            return {"success": False, "method": "autocomplete", "error": str(e)}

    def _find_best_option_match(self, raw_options: list[dict[str, str]], normalized_target: str) -> str | None:
        """یافتن بهترین تطابق بین گزینه‌ها"""
        best_value = None
        for option in raw_options:
            option_text = str(option.get("text") or "").strip()
            option_value = str(option.get("value") or "").strip()
            normalized_text = self._normalize_text(option_text)
            normalized_value = self._normalize_text(option_value)

            if normalized_text == "undefined" or normalized_value == "undefined":
                continue

            if normalized_target == normalized_text or normalized_target == normalized_value:
                return option_value or option_text

            if (
                normalized_target in normalized_text
                or normalized_target in normalized_value
                or normalized_text in normalized_target
            ):
                best_value = option_value or option_text

        return best_value

    async def _select_from_options(self, selectors: list[str], value: str) -> bool:
        """انتخاب گزینه از منوی کشویی بر اساس متن یا مقدار"""
        if not value:
            return False

        value_text = str(value).strip()
        normalized_target = self._normalize_text(value_text)

        for selector in selectors:
            try:
                visible_selector = self._make_visible_selector(selector)
                element = await self.page.query_selector(visible_selector)
                if not element:
                    continue

                success = False
                try:
                    await self.page.select_option(visible_selector, label=value_text)
                    success = True
                except Exception:
                    try:
                        await self.page.select_option(visible_selector, value=value_text)
                        success = True
                    except Exception:
                        raw_options = await self._read_select_options(selector)
                        if raw_options:
                            best_value = self._find_best_option_match(raw_options, normalized_target)
                            if best_value:
                                try:
                                    await self.page.select_option(visible_selector, value=best_value)
                                    success = True
                                except Exception:
                                    try:
                                        await self.page.select_option(visible_selector, label=best_value)
                                        success = True
                                    except Exception:
                                        pass

                if success:
                    try:
                        await self.page.eval_on_selector(
                            visible_selector,
                            "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }",
                        )
                    except Exception:
                        pass
                    return True

                logger.info(
                    "location_option_match_failed",
                    extra={
                        "extra_fields": {
                            "selector": selector,
                            "visible_selector": visible_selector,
                            "target": value_text,
                        }
                    },
                )
            except Exception:
                continue

        return False

    async def _find_map_search_input(self, prefix: str) -> str | None:
        """یافتن انتخابگر ورودی جستجوی نقشه"""
        extra_aliases: list[str] = ["2"]
        if prefix.lower() == "origin":
            extra_aliases.append("Source")
        if prefix.lower() == "destination":
            extra_aliases.append("Dest")

        selectors = self._build_formatted_selectors(
            LocationSelectors.MAP_SEARCH_TEMPLATES,
            prefix=prefix,
            extra_aliases=extra_aliases,
        )

        for selector in selectors:
            visible_selector = self._make_visible_selector(selector)
            element = await self.page.query_selector(visible_selector)
            if element:
                return visible_selector

        return None

    async def _make_http_request(self, url: str, params: dict, headers: dict, timeout: float = 5.0) -> Any:
        """اجرای درخواست HTTP با قابلیت تلاش مجدد و استفاده از پروکسی در صورت شکست"""
        import aiohttp

        from app.automation.proxy_rotator import get_proxy_rotator

        # 1. تلاش برای درخواست مستقیم (سریع‌ترین حالت در صورت در دسترس بودن شبکه)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.debug(f"Direct HTTP request to {url} failed: {e}. Retrying via proxy if available...")

        # 2. تلاش با استفاده از پروکسی‌های چرخشی در صورت شکست مستقیم
        proxy_info = await get_proxy_rotator().get_next()
        if proxy_info:
            try:
                if proxy_info.protocol in ("http", "https"):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url,
                            params=params,
                            headers=headers,
                            proxy=proxy_info.full_url,
                            timeout=aiohttp.ClientTimeout(total=timeout),
                        ) as resp:
                            if resp.status == 200:
                                return await resp.json()
            except Exception as proxy_err:
                logger.warning(f"Proxy HTTP request to {url} failed: {proxy_err}")

        return None

    async def _geocode_address(self, location_data: dict[str, Any]) -> dict[str, float] | None:
        """تبدیل آدرس به مختصات با استفاده از سرویس خارجی"""
        province = str(location_data.get("province", "") or "").strip()
        city = str(location_data.get("city", "") or "").strip()
        address_text = str(location_data.get("address", "") or "").strip()
        candidates = [
            ", ".join(part for part in [province, city, address_text] if part),
            ", ".join(part for part in [city, address_text] if part),
            address_text,
        ]
        candidates = [candidate for candidate in candidates if candidate]

        url = "https://nominatim.openstreetmap.org/search"
        headers = {"User-Agent": "UTCMS-Automation/1.0"}

        for candidate in candidates:
            params = {"q": f"{candidate}, Iran", "format": "json", "limit": 1}
            try:
                data = await self._make_http_request(url, params=params, headers=headers, timeout=4.0)
                if data:
                    return {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
            except Exception as e:
                logger.debug(f"Candidate geocoding failed for {candidate}: {e}")

        return None

    async def _reverse_geocode(self, lat: float, lng: float) -> dict[str, str] | None:
        """تبدیل مختصات به آدرس (استان، شهر، منطقه) برای پر کردن خودکار فیلدها"""
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            "lat": lat,
            "lng": lng,
            "format": "json",
            "accept-language": "fa",
            "zoom": 10,
        }
        headers = {"User-Agent": "UTCMS-Automation/1.0"}

        try:
            data = await self._make_http_request(url, params=params, headers=headers, timeout=4.0)
            if data:
                address = data.get("address", {})

                province = address.get("state") or address.get("province") or address.get("county") or ""

                city = (
                    address.get("city")
                    or address.get("town")
                    or address.get("village")
                    or address.get("municipality")
                    or ""
                )

                district = address.get("suburb") or address.get("district") or address.get("neighbourhood") or ""

                result = {}
                if province:
                    result["province"] = province
                if city:
                    result["city"] = city
                if district:
                    result["district"] = district

                return result if result else None
        except Exception as e:
            logger.warning(
                "reverse_geocoding_failed",
                extra={"extra_fields": {"lat": lat, "lng": lng, "error": str(e)}},
            )

        return None


class RouteCalculator:
    """محاسبه مسیر بین دو نقطه"""

    def __init__(self, page: Page):
        self.page = page

    async def calculate_distance(self, origin: GeoCoordinate, destination: GeoCoordinate) -> dict[str, Any]:
        """محاسبه مسافت و زمان بین دو نقطه"""
        from app.automation.script_loader import script_loader

        script = script_loader.load("calculate_distance")

        try:
            result = await self.page.evaluate(
                script,
                {
                    "originLat": origin.latitude,
                    "originLng": origin.longitude,
                    "destLat": destination.latitude,
                    "destLng": destination.longitude,
                },
            )
            return result or {}
        except Exception:
            return self._calculate_haversine(origin, destination)

    def _calculate_haversine(self, origin: GeoCoordinate, destination: GeoCoordinate) -> dict[str, Any]:
        """محاسبه فاصله با استفاده از فرمول هاورسین"""
        import math

        R = 6371  # شعاع زمین به کیلومتر

        lat1 = math.radians(origin.latitude)
        lat2 = math.radians(destination.latitude)
        dlat = math.radians(destination.latitude - origin.latitude)
        dlon = math.radians(destination.longitude - origin.longitude)

        a = math.sin(dlat / 2) * math.sin(dlat / 2) + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) * math.sin(
            dlon / 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        distance = R * c

        duration_min = (distance / 60) * 60  # فرض ۶۰ کیلومتر بر ساعت

        return {
            "distance": f"{distance:.2f} km",
            "distance_value": distance * 1000,
            "duration": f"{int(duration_min)} mins",
            "duration_value": duration_min * 60,
            "method": "haversine",
        }
