"""
انتخابگر مکان با قابلیت جایگزینی: نقشه ← منوی کشویی ← ورودی متنی
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional

from playwright.async_api import Page

from app.automation.map_controller import MapController, GeoCoordinate
from app.core.exceptions import LocationSelectionError
from app.core.logging import monitoring_extra
from app.automation.script_loader import script_loader
from app.automation.selectors import LocationSelectors

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
    def _unique_preserve_order(items: List[str]) -> List[str]:
        seen = set()
        output: List[str] = []
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            output.append(item)
        return output

    def _additional_prefix_aliases(self, prefix: str) -> List[str]:
        lowered = (prefix or "").lower()
        if lowered == "origin":
            return ["Source"]
        if lowered == "destination":
            return ["Dest"]
        return []

    def _build_formatted_selectors(
        self,
        templates: List[str],
        prefix: str,
        extra_aliases: Optional[List[str]] = None,
    ) -> List[str]:
        aliases = [prefix]
        aliases.extend(self._additional_prefix_aliases(prefix))
        if extra_aliases:
            aliases.extend(extra_aliases)

        selectors: List[str] = []
        for alias in self._unique_preserve_order(aliases):
            prefix_lower = alias.lower()
            for template in templates:
                try:
                    selectors.append(template.format(prefix=alias, prefix_lower=prefix_lower))
                except KeyError:
                    continue

        return self._unique_preserve_order(selectors)

    async def _fill_input_like(self, selector: str, value: str) -> bool:
        if not value:
            return False

        try:
            await self.page.fill(selector, value)
            return True
        except Exception:
            pass

        try:
            locator = self.page.locator(selector).first
            if await locator.count() == 0:
                return False
            await locator.fill(value)
            return True
        except Exception:
            pass

        try:
            updated = await self.page.eval_on_selector(
                selector,
                """(el, rawValue) => {
                    const value = String(rawValue ?? '');
                    if (!el) return false;
                    if ('value' in el) {
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                        return true;
                    }
                    return false;
                }""",
                value,
            )
            return bool(updated)
        except Exception:
            return False

    async def _scroll_into_view(self, selector: str) -> bool:
        try:
            await self.page.eval_on_selector(
                selector,
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
            return bool(await self.page.is_visible(selector))
        except Exception:
            return False

    async def _ensure_location_tab_active(self, prefix: str) -> None:
        tab_ids = {
            "Origin": "pills-5-tab",
            "Destination": "pills-6-tab",
        }
        pane_ids = {
            "Origin": "pills-5",
            "Destination": "pills-6",
        }
        tab_id = tab_ids.get(prefix)
        pane_id = pane_ids.get(prefix)
        if not tab_id or not pane_id:
            return

        tab_selector = f"#{tab_id}"
        pane_selector = f"#{pane_id}"
        if not tab_selector or not pane_selector:
            return

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
            pass

        try:
            await self.page.click(tab_selector)
            await asyncio.sleep(0.4)
        except Exception:
            pass

    async def _read_select_options(self, selector: str) -> List[Dict[str, str]]:
        try:
            options = await self.page.eval_on_selector_all(
                f"{selector} option",
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
        selectors: List[str],
        *,
        min_real_options: int = 1,
        timeout_ms: int = 12000,
    ) -> bool:
        deadline = asyncio.get_running_loop().time() + max(1.0, timeout_ms / 1000)
        while asyncio.get_running_loop().time() < deadline:
            for selector in selectors:
                options = await self._read_select_options(selector)
                real_options = [
                    option for option in options
                    if self._normalize_text(option.get("text", "")) not in {"", "انتخابکنید...", "انتخابکنید", "undefined"}
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

    async def _inspect_select_runtime(self, selector: str) -> Dict[str, Any]:
        options = await self._read_select_options(selector)
        placeholder_count = 0
        undefined_count = 0
        real_options: List[Dict[str, str]] = []

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
        selectors: Dict[str, List[str]],
        prefix: str,
    ) -> Dict[str, Any]:
        province_runtime: List[Dict[str, Any]] = []
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

    async def select_location(
        self,
        location_data: Dict[str, Any],
        origin: bool = True
    ) -> Dict[str, Any]:
        """
        انتخاب مکان با استفاده از بهترین روش موجود
        اولویت: ۱. مختصات صریح (کلیک کاربر) ۲. نقشه ۳. منوی کشویی ۴. ورودی متنی

        Args:
            location_data: {
                "province": "تهران",
                "city": "تهران",
                "district": "منطقه ۱",
                "address": "خیابان آزادی",
                "coordinates": {"lat": 35.6892, "lng": 51.3890}
            }
            origin: True برای مبدا، False برای مقصد

        Returns:
            نتیجه انتخاب همراه با روش استفاده شده
        """
        prefix = "Origin" if origin else "Destination"
        logger.info(
            "location_selection_started",
            extra={"extra_fields": {"prefix": prefix, "location_data": location_data}},
        )
        coordinates = location_data.get("coordinates")
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
        # ۲. انتخاب از آدرس‌های ذخیره‌شده / علاقه‌مندی اگر موجود باشد
        favorite_result = await self._try_favorite_address_selection(location_data, prefix)
        if favorite_result["success"]:
            return favorite_result

        logger.warning(
            "favorite_address_selection_failed_falling_back",
            extra={"extra_fields": {"prefix": prefix, "error": favorite_result.get("error")}},
        )

        # ۳. نقشه با جستجوی داخلی
        map_search_result = {"success": False, "error": "Not attempted"}
        if not coordinates or coordinates.get("lat") is None or coordinates.get("lng") is None:
            map_search_result = await self._try_internal_map_search(location_data, prefix)
            if map_search_result["success"]:
                return map_search_result

            logger.warning(
                "internal_map_search_failed_falling_back",
                extra={"extra_fields": {"prefix": prefix, "error": map_search_result.get("error")}},
            )

        # ۵.۵ Dropdown Selection (if earlier methods failed)
        if not coordinates or coordinates.get("lat") is None or coordinates.get("lng") is None:
            if dropdown_runtime.get("viable"):
                dropdown_result = await self._try_dropdown_selection(location_data, prefix, selectors=selectors)
                if dropdown_result["success"]:
                    return dropdown_result
                logger.warning(
                    "dropdown_selection_failed_falling_back",
                    extra={"extra_fields": {"prefix": prefix, "error": dropdown_result.get("error"), "runtime": dropdown_runtime}},
                )
            else:
                logger.info(
                    "dropdown_selection_skipped",
                    extra={"extra_fields": {"prefix": prefix, "runtime": dropdown_runtime}},
                )

        inferred_coordinates = None
        if not coordinates or coordinates.get("lat") is None or coordinates.get("lng") is None:
            inferred_coordinates = await self._geocode_address(location_data)
            if inferred_coordinates:
                coordinates = inferred_coordinates
                location_data = {
                    **location_data,
                    "coordinates": inferred_coordinates,
                }
                logger.info(
            "location_geocoded_for_fallback",
                    extra={"extra_fields": {"prefix": prefix, "location_data": location_data}},
                )

        # ۴. اگر مختصات صریح داریم، hidden/map fallback
        explicit_coords_result = {"success": False, "error": "بدون مختصات"}
        if coordinates and coordinates.get("lat") is not None and coordinates.get("lng") is not None:
            explicit_coords_result = await self._try_explicit_coordinates(location_data, prefix)
            if explicit_coords_result["success"]:
                return explicit_coords_result
            logger.info(
                "explicit_coordinates_failed_falling_back",
                extra={"extra_fields": {"prefix": prefix, "error": explicit_coords_result.get("error")}},
            )

        # ۵. نقشه با مختصات
        map_result = {"success": False, "error": "بدون مختصات"}
        if coordinates and coordinates.get("lat") is not None and coordinates.get("lng") is not None:
            map_result = await self._try_map_selection(location_data, prefix)
            if map_result["success"]:
                if inferred_coordinates:
                    map_result["method"] = "map_geocoded"
                return map_result
            logger.warning(
                "map_selection_failed_falling_back",
                extra={"extra_fields": {"prefix": prefix, "error": map_result.get("error")}},
            )

        # ۶. Fallback نهایی: Dropdown اگر تا اینجا نیامده بود
        if (coordinates and coordinates.get("lat") is not None and coordinates.get("lng") is not None) and not inferred_coordinates:
            if dropdown_runtime.get("viable"):
                dropdown_result = await self._try_dropdown_selection(location_data, prefix, selectors=selectors)
                if dropdown_result["success"]:
                    return dropdown_result
                logger.warning(
                    "dropdown_selection_failed_falling_back",
                    extra={"extra_fields": {"prefix": prefix, "error": dropdown_result.get("error"), "runtime": dropdown_runtime}},
                )
            else:
                logger.info(
                    "dropdown_selection_skipped",
                    extra={"extra_fields": {"prefix": prefix, "runtime": dropdown_runtime}},
                )

        # ۷. Fallback نهایی: ورودی متنی
        text_result = await self._try_text_input(location_data, prefix)
        if text_result["success"]:
            return text_result

        raise LocationSelectionError(
            f"همه روش‌های انتخاب مکان ({prefix}) با شکست مواجه شدند. "
            f"Favorite: {favorite_result.get('error')} | "
            f"MapSearch: {map_search_result.get('error')} | "
            f"نقشه: {map_result.get('error')} | "
            f"Dropdown: {dropdown_result.get('error')} | "
            f"متن: {text_result.get('error')}"
        )

    async def _fill_coordinate_hidden_fields(self, lat: float, lng: float, prefix: str) -> bool:
        """
        تلاش برای یافتن و پر کردن hidden fields مربوط به مختصات
        """
        hidden_selectors = [
            f'input[name="{prefix}Lat"]',
            f'input[name="{prefix}Lng"]',
            f'input[name="{prefix}Latitude"]',
            f'input[name="{prefix}Longitude"]',
            f'input[id="{prefix.lower()}_lat"]',
            f'input[id="{prefix.lower()}_lng"]',
            f'input[name*="Coordinate"][name*="{prefix.lower()}"]',
        ]

        lat_filled = False
        lng_filled = False

        for selector in hidden_selectors:
            if "Lat" in selector or "Latitude" in selector or "_lat" in selector:
                if await self._fill_input_like(selector, str(lat)):
                    lat_filled = True
            elif "Lng" in selector or "Longitude" in selector or "_lng" in selector:
                if await self._fill_input_like(selector, str(lng)):
                    lng_filled = True

        return lat_filled and lng_filled

    async def _inject_coordinates_via_js(self, lat: float, lng: float, prefix: str) -> bool:
        """
        تلاش برای تزریق مستقیم مختصات به inputهای مخفی از طریق JavaScript
        """
        injection_script = f"""
        () => {{
            const lat = {lat};
            const lng = {lng};
            const prefix = "{prefix.lower()}";

            // جستجو برای input های hidden
            const inputs = document.querySelectorAll('input[type="hidden"]');
            let found = false;

            inputs.forEach(input => {{
                const name = (input.name || '').toLowerCase();
                const id = (input.id || '').toLowerCase();

                if ((name.includes('lat') || id.includes('lat')) &&
                    (name.includes(prefix) || id.includes(prefix) ||
                     name.includes('origin') || name.includes('source') ||
                     name.includes('dest') || name.includes('magsad'))) {{
                    input.value = lat;
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    found = true;
                }}
                if ((name.includes('lng') || name.includes('lon') ||
                     id.includes('lng') || id.includes('lon')) &&
                    (name.includes(prefix) || id.includes(prefix) ||
                     name.includes('origin') || name.includes('source') ||
                     name.includes('dest') || name.includes('magsad'))) {{
                    input.value = lng;
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    found = true;
                }}
            }});

            return found;
        }}
        """

        injected = await self.page.evaluate(injection_script)
        return bool(injected)

    async def _try_explicit_coordinates(
        self,
        location_data: Dict[str, Any],
        prefix: str
    ) -> Dict[str, Any]:
        """
        تلاش برای استفاده مستقیم از مختصات با پر کردن hidden fields
        یا injection مختصات به فرم UTCMS
        """
        coordinates = location_data.get("coordinates")
        if not coordinates:
            return {"success": False, "method": "explicit_coords", "error": "مختصات موجود نیست"}

        try:
            lat = coordinates.get("lat")
            lng = coordinates.get("lng")
            
            if lat is None or lng is None:
                return {"success": False, "method": "explicit_coords", "error": "مختصات ناقص"}

            # ۱. تلاش برای یافتن hidden fields مربوط به مختصات
            if await self._fill_coordinate_hidden_fields(lat, lng, prefix):
                return {
                    "success": True,
                    "method": "explicit_coordinates",
                    "coordinates": {"lat": lat, "lng": lng},
                }

            # ۲. اگر hidden fields نبود، تلاش برای injection با JavaScript
            if await self._inject_coordinates_via_js(lat, lng, prefix):
                return {
                    "success": True,
                    "method": "explicit_coordinates_injected",
                    "coordinates": {"lat": lat, "lng": lng},
                }

            return {
                "success": False,
                "method": "explicit_coords",
                "error": "hidden fields برای مختصات یافت نشد",
            }

        except Exception as e:
            return {"success": False, "method": "explicit_coords", "error": str(e)}

    async def _try_map_selection(
        self,
        location_data: Dict[str, Any],
        prefix: str
    ) -> Dict[str, Any]:
        """تلاش برای انتخاب مکان با استفاده از نقشه"""

        # تشخیص وجود نقشه
        map_type = await self.map_controller.detect_map_type()

        if not map_type:
            return {"success": False, "method": "map", "error": "نقشه‌ای یافت نشد"}

        coordinates = location_data.get("coordinates")
        if not coordinates:
            return {"success": False, "method": "map", "error": "مختصات صریح کاربر ارسال نشده است"}

        try:
            location = GeoCoordinate(
                latitude=coordinates["lat"],
                longitude=coordinates["lng"],
                address=location_data.get("address"),
            )

            selected = await self.map_controller.select_on_map(
                selector=None,
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

            return {
                "success": True,
                "method": "map",
                "coordinates": {
                    "lat": location.latitude,
                    "lng": location.longitude,
                },
                "map_type": map_type,
            }

        except Exception as e:
            return {"success": False, "method": "map", "error": str(e)}

    async def _try_dropdown_selection(
        self,
        location_data: Dict[str, Any],
        prefix: str,
        *,
        selectors: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        تلاش برای انتخاب آبشاری
        استان ← شهر ← منطقه
        """

        try:
            await self._ensure_location_tab_active(prefix)

            # الگوهای انتخابگر رایج (نسخه‌های مختلف UTCMS)
            selectors = selectors or {
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

            await self._wait_for_select_options(selectors["province"], timeout_ms=10000)
            for selector in selectors["province"][:3]:
                await self._log_select_diagnostics(selector, f"{prefix} province", str(location_data.get("province", "")))

            # انتخاب استان
            province_selectors = selectors["province"]
            province_selected = await self._select_from_options(
                province_selectors,
                location_data.get("province", "")
            )

            if not province_selected:
                return {
                    "success": False,
                    "method": "dropdown",
                    "error": "انتخاب استان با شکست مواجه شد"
                }

            city_options_ready = await self._wait_for_select_options(
                selectors["city"],
                timeout_ms=15000,
            )
            if not city_options_ready:
                logger.warning(
                    "location_city_options_not_ready",
                    extra={"extra_fields": {"prefix": prefix, "location_data": location_data}},
                )
            for selector in selectors["city"][:3]:
                await self._log_select_diagnostics(selector, f"{prefix} city", str(location_data.get("city", "")))

            # انتخاب شهر
            city_selectors = selectors["city"]
            city_selected = await self._select_from_options(
                city_selectors,
                location_data.get("city", "")
            )

            if not city_selected:
                return {
                    "success": False,
                    "method": "dropdown",
                    "error": "انتخاب شهر با شکست مواجه شد"
                }

            await self._wait_for_select_options(
                selectors["district"],
                timeout_ms=5000,
            )

            # انتخاب منطقه (اختیاری)
            district_selectors = selectors["district"]
            await self._select_from_options(
                district_selectors,
                location_data.get("district", "")
            )

            # پر کردن آدرس متنی اگر وجود داشته باشد
            address_selectors = self._build_formatted_selectors(
                LocationSelectors.ADDRESS_TEMPLATES,
                prefix=prefix,
            )

            for selector in address_selectors:
                try:
                    logger.info(
                        "location_address_fill_attempt",
                        extra={
                            "extra_fields": {
                                "prefix": prefix,
                                "selector": selector,
                                "address": location_data.get("address", ""),
                            }
                        },
                    )
                    filled = await self._fill_input_like(selector, location_data.get("address", ""))
                    if filled:
                        break
                except Exception:
                    continue

            return {
                "success": True,
                "method": "dropdown",
                "province": location_data.get("province"),
                "city": location_data.get("city"),
                "district": location_data.get("district")
            }

        except Exception as e:
            return {"success": False, "method": "dropdown", "error": str(e)}

    async def _try_favorite_address_selection(
        self,
        location_data: Dict[str, Any],
        prefix: str,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_location_tab_active(prefix)
            grid_id = "gridfulSenderAddress" if prefix == "Origin" else "gridfulReceiverAddress"
            button_id = "selectSenderAddress" if prefix == "Origin" else "selectReceiverAddress"
            grid_selector = f"#{grid_id}"
            button_selector = f"#{button_id}"
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

            selector = f"{grid_selector} tbody tr:nth-child({best_index + 1}) {button_selector}"
            await self._scroll_into_view(selector)
            await self.page.click(selector)
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
                await self.page.locator(f"xpath=//select[@id='{select_selector.lstrip('#')}']/following-sibling::span[contains(@class,'select2')][1]//span[contains(@class,'select2-selection')]").click(timeout=2500)
            await asyncio.sleep(0.3)
            search_input = self.page.locator("input.select2-search__field").last
            await search_input.fill(search_value)
            await asyncio.sleep(1.0)
            results = self.page.locator(".select2-results__option")
            count = await results.count()
            for idx in range(count):
                option = results.nth(idx)
                text = self._normalize_text(await option.inner_text())
                target = self._normalize_text(search_value)
                if target and (target in text or text in target):
                    await option.click()
                    await asyncio.sleep(0.5)
                    return True
            if count > 0:
                await results.nth(0).click()
                await asyncio.sleep(0.5)
                return True
        except Exception:
            return False
        return False

    async def _wait_for_non_empty_text(self, selectors: List[str], timeout_ms: int = 10000) -> Optional[str]:
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

    async def _try_internal_map_search(
        self,
        location_data: Dict[str, Any],
        prefix: str,
    ) -> Dict[str, Any]:
        try:
            await self._ensure_location_tab_active(prefix)
            map_city_id = "MapCity" if prefix == "Origin" else "MapCity2"
            address_search_id = "AddressSearch" if prefix == "Origin" else "AddressSearch2"
            search_button_id = "btnsearchAddressSource" if prefix == "Origin" else "btnsearchAddressDest"
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

    async def _try_text_input(
        self,
        location_data: Dict[str, Any],
        prefix: str
    ) -> Dict[str, Any]:
        """تلاش برای ورودی متنی با تکمیل خودکار"""

        try:
            # یافتن ورودی تکمیل خودکار (input/select)
            input_selectors = self._build_formatted_selectors(
                LocationSelectors.INPUT_TEMPLATES,
                prefix=prefix,
                extra_aliases=["2"],
            )

            search_text = f"{location_data.get('city', '')} {location_data.get('address', '')}"
            search_text = search_text.strip()
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

                    # انتظار برای تکمیل خودکار
                    await asyncio.sleep(1)

                    # کلیک روی اولین پیشنهاد
                    suggestion_selectors = LocationSelectors.SUGGESTION_SELECTORS

                    for sugg_selector in suggestion_selectors:
                        sugg = await self.page.query_selector(sugg_selector)
                        if sugg:
                            await sugg.click()
                            return {
                                "success": True,
                                "method": "autocomplete",
                                "search": search_text
                            }

                except Exception:
                    continue

            return {
                "success": False,
                "method": "autocomplete",
                "error": "هیچ پیشنهادی یافت نشد"
            }

        except Exception as e:
            return {"success": False, "method": "autocomplete", "error": str(e)}

    def _find_best_option_match(self, raw_options: List[Dict[str, str]], normalized_target: str) -> Optional[str]:
        """یافتن بهترین تطابق بین گزینه‌ها"""
        best_value = None
        for option in raw_options:
            option_text = str(option.get("text") or "").strip()
            option_value = str(option.get("value") or "").strip()
            normalized_text = self._normalize_text(option_text)
            normalized_value = self._normalize_text(option_value)

            if normalized_text == "undefined" or normalized_value == "undefined":
                continue

            if (
                normalized_target == normalized_text
                or normalized_target == normalized_value
            ):
                return option_value or option_text

            if (
                normalized_target in normalized_text
                or normalized_target in normalized_value
                or normalized_text in normalized_target
            ):
                best_value = option_value or option_text

        return best_value

    async def _select_from_options(
        self,
        selectors: List[str],
        value: str
    ) -> bool:
        """انتخاب گزینه از منوی کشویی بر اساس متن یا مقدار"""
        if not value:
            return False

        value_text = str(value).strip()
        normalized_target = self._normalize_text(value_text)

        for selector in selectors:
            try:
                # بررسی وجود عنصر
                element = await self.page.query_selector(selector)
                if not element:
                    continue

                try:
                    await self.page.select_option(selector, label=value_text)
                    return True
                except Exception:
                    pass

                try:
                    await self.page.select_option(selector, value=value_text)
                    return True
                except Exception:
                    pass

                # دریافت تمام گزینه‌ها
                raw_options = await self._read_select_options(selector)
                if not raw_options:
                    continue

                best_value = self._find_best_option_match(raw_options, normalized_target)

                if best_value:
                    try:
                        await self.page.select_option(selector, value=best_value)
                        return True
                    except Exception:
                        try:
                            await self.page.select_option(selector, label=best_value)
                            return True
                        except Exception:
                            pass

                logger.info(
                    "location_option_match_failed",
                    extra={
                        "extra_fields": {
                            "selector": selector,
                            "target": value_text,
                            "available_options": raw_options[:20],
                        }
                    },
                )

            except Exception:
                continue

        return False

    async def _find_map_search_input(self, prefix: str) -> Optional[str]:
        """یافتن انتخابگر ورودی جستجوی نقشه"""
        extra_aliases: List[str] = ["2"]
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
            element = await self.page.query_selector(selector)
            if element:
                return selector

        return None

    async def _geocode_address(self, location_data: Dict[str, Any]) -> Optional[Dict[str, float]]:
        """
        تبدیل آدرس به مختصات با استفاده از سرویس خارجی
        """
        import aiohttp

        province = str(location_data.get("province", "") or "").strip()
        city = str(location_data.get("city", "") or "").strip()
        address_text = str(location_data.get("address", "") or "").strip()
        candidates = [
            ", ".join(part for part in [province, city, address_text] if part),
            ", ".join(part for part in [city, address_text] if part),
            address_text,
        ]
        candidates = [candidate for candidate in candidates if candidate]

        try:
            # استفاده از Nominatim (OpenStreetMap)
            async with aiohttp.ClientSession() as session:
                url = "https://nominatim.openstreetmap.org/search"
                headers = {
                    "User-Agent": "UTCMS-Automation/1.0"
                }

                for candidate in candidates:
                    params = {
                        "q": f"{candidate}, Iran",
                        "format": "json",
                        "limit": 1
                    }
                    async with session.get(url, params=params, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data:
                                return {
                                    "lat": float(data[0]["lat"]),
                                    "lng": float(data[0]["lon"])
                                }
        except Exception as e:
            logger.warning(
                "geocoding_failed",
                extra={"extra_fields": {"address_candidates": candidates, "error": str(e)}},
            )

        return None

    async def _reverse_geocode(self, lat: float, lng: float) -> Optional[Dict[str, str]]:
        """
        تبدیل مختصات به آدرس (استان، شهر، منطقه)
        برای پر کردن خودکار فیلدها از روی نقطه کلیک شده
        """
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                url = "https://nominatim.openstreetmap.org/reverse"
                params = {
                    "lat": lat,
                    "lon": lng,
                    "format": "json",
                    "accept-language": "fa",
                    "zoom": 10,
                }
                headers = {
                    "User-Agent": "UTCMS-Automation/1.0"
                }

                async with session.get(url, params=params, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        address = data.get("address", {})
                        
                        # استخراج استان
                        province = (
                            address.get("state") or 
                            address.get("province") or 
                            address.get("county") or
                            ""
                        )
                        
                        # استخراج شهر
                        city = (
                            address.get("city") or 
                            address.get("town") or 
                            address.get("village") or
                            address.get("municipality") or
                            ""
                        )
                        
                        # استخراج منطقه
                        district = (
                            address.get("suburb") or 
                            address.get("district") or 
                            address.get("neighbourhood") or
                            ""
                        )
                        
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

    async def calculate_distance(
        self,
        origin: GeoCoordinate,
        destination: GeoCoordinate
    ) -> Dict[str, Any]:
        """
        محاسبه مسافت و زمان بین دو نقطه

        استفاده از جاوااسکریپت برای محاسبه یا استخراج از صفحه
        """

        script = script_loader.load("calculate_distance")

        try:
            result = await self.page.evaluate(script, {
                "originLat": origin.latitude,
                "originLng": origin.longitude,
                "destLat": destination.latitude,
                "destLng": destination.longitude
            })
            return result or {}
        except Exception:
            # محاسبه با استفاده از پایتون
            return self._calculate_haversine(origin, destination)

    def _calculate_haversine(
        self,
        origin: GeoCoordinate,
        destination: GeoCoordinate
    ) -> Dict[str, Any]:
        """محاسبه فاصله با استفاده از فرمول هاورسین"""
        import math

        R = 6371  # شعاع زمین به کیلومتر

        lat1 = math.radians(origin.latitude)
        lat2 = math.radians(destination.latitude)
        dlat = math.radians(destination.latitude - origin.latitude)
        dlon = math.radians(destination.longitude - origin.longitude)

        a = (math.sin(dlat/2) * math.sin(dlat/2) +
             math.cos(lat1) * math.cos(lat2) *
             math.sin(dlon/2) * math.sin(dlon/2))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        distance = R * c

        # تخمین زمان
        duration_min = (distance / 60) * 60  # فرض ۶۰ کیلومتر بر ساعت

        return {
            "distance": f"{distance:.2f} km",
            "distance_value": distance * 1000,
            "duration": f"{int(duration_min)} mins",
            "duration_value": duration_min * 60,
            "method": "haversine"
        }
