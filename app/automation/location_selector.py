"""
انتخابگر مکان با قابلیت جایگزینی: نقشه ← منوی کشویی ← ورودی متنی
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from playwright.async_api import Page

from app.automation.map_controller import GeoCoordinate, MapController
from app.automation.selectors import LocationSelectors
from app.core.exceptions import LocationSelectionError
from app.core.logging import monitoring_extra

logger = logging.getLogger(__name__)

# کش در سطح پروسس برای نتایج ژئوکدینگ
_geocoding_cache: dict[str, dict[str, float]] = {}

# مختصات شهرهای مهم ایران جهت ژئوکدینگ محلی سریع و بدون نیاز به اینترنت
IRAN_CITY_COORDINATES: dict[str, dict[str, float]] = {
    "تهران": {"lat": 35.6892, "lng": 51.3890},
    "ری": {"lat": 35.5901, "lng": 51.4357},
    "شمرانات": {"lat": 35.8083, "lng": 51.4283},
    "اسلامشهر": {"lat": 35.5614, "lng": 51.2325},
    "شهریار": {"lat": 35.6597, "lng": 51.0592},
    "قدس": {"lat": 35.7208, "lng": 51.1097},
    "ملارد": {"lat": 35.6667, "lng": 50.9833},
    "ورامین": {"lat": 35.3250, "lng": 51.6492},
    "پاکدشت": {"lat": 35.4817, "lng": 51.6803},
    "دماوند": {"lat": 35.7178, "lng": 52.0650},
    "رباطکریم": {"lat": 35.4847, "lng": 51.0828},
    "بهارستان": {"lat": 35.5386, "lng": 51.1642},
    "اصفهان": {"lat": 32.6546, "lng": 51.6680},
    "کاشان": {"lat": 33.9850, "lng": 51.4100},
    "خمینیشهر": {"lat": 32.6844, "lng": 51.5361},
    "نجفآباد": {"lat": 32.6339, "lng": 51.3486},
    "شاهینشهر": {"lat": 32.8625, "lng": 51.5492},
    "لنجان": {"lat": 32.4333, "lng": 51.3167},
    "فلاورجان": {"lat": 32.5583, "lng": 51.5103},
    "شهرضا": {"lat": 32.0089, "lng": 51.8711},
    "گلپایگان": {"lat": 33.4536, "lng": 50.2883},
    "مشهد": {"lat": 36.2972, "lng": 59.6067},
    "نیشابور": {"lat": 36.2133, "lng": 58.7958},
    "سبزوار": {"lat": 36.2167, "lng": 57.6833},
    "تربتحیدریه": {"lat": 35.2742, "lng": 59.2194},
    "قوچان": {"lat": 37.1064, "lng": 58.5095},
    "کاشمر": {"lat": 35.2383, "lng": 58.4656},
    "تربتجام": {"lat": 35.2439, "lng": 60.6225},
    "تبریز": {"lat": 38.0962, "lng": 46.2738},
    "مراغه": {"lat": 37.3917, "lng": 46.2394},
    "مرند": {"lat": 38.4286, "lng": 45.7744},
    "میانه": {"lat": 37.4208, "lng": 47.6972},
    "اهر": {"lat": 38.4778, "lng": 47.0694},
    "بناب": {"lat": 37.3403, "lng": 46.0561},
    "شیراز": {"lat": 29.5918, "lng": 52.5837},
    "مرودشت": {"lat": 29.8742, "lng": 52.8025},
    "جهرم": {"lat": 28.5000, "lng": 53.5600},
    "فسا": {"lat": 28.9383, "lng": 53.6486},
    "کازرون": {"lat": 29.6194, "lng": 51.6542},
    "لارستان": {"lat": 27.6833, "lng": 54.3333},
    "اهواز": {"lat": 31.3183, "lng": 48.6706},
    "دزفول": {"lat": 32.3811, "lng": 48.4058},
    "آبادان": {"lat": 30.3392, "lng": 48.3044},
    "خرمشهر": {"lat": 30.4397, "lng": 48.1794},
    "اندیمشک": {"lat": 32.4600, "lng": 48.3500},
    "ایذه": {"lat": 31.8333, "lng": 49.8667},
    "شوش": {"lat": 32.1942, "lng": 47.2436},
    "ماهشهر": {"lat": 30.5589, "lng": 49.1917},
    "بهبهان": {"lat": 30.5958, "lng": 50.2417},
    "ساری": {"lat": 36.5633, "lng": 53.0601},
    "بابل": {"lat": 36.5508, "lng": 52.6789},
    "آمل": {"lat": 36.4678, "lng": 52.3506},
    "قائمشهر": {"lat": 36.4628, "lng": 52.8606},
    "بهشهر": {"lat": 36.6925, "lng": 53.5383},
    "تنکابن": {"lat": 36.8167, "lng": 50.8000},
    "کرج": {"lat": 35.8327, "lng": 50.9915},
    "هشتگرد": {"lat": 35.9628, "lng": 50.6828},
    "نظرآباد": {"lat": 35.9525, "lng": 50.6053},
    "فردیس": {"lat": 35.7236, "lng": 50.9828},
    "رشت": {"lat": 37.2808, "lng": 49.5831},
    "بندرانزلی": {"lat": 37.4722, "lng": 49.4622},
    "لاهیجان": {"lat": 37.2000, "lng": 50.0000},
    "لنگرود": {"lat": 37.1903, "lng": 50.1539},
    "تالش": {"lat": 37.8000, "lng": 48.9000},
    "کرمان": {"lat": 30.2839, "lng": 57.0834},
    "سیرجان": {"lat": 29.4522, "lng": 55.6814},
    "رفسنجان": {"lat": 30.4067, "lng": 55.9939},
    "جیرفت": {"lat": 28.6747, "lng": 57.7403},
    "بم": {"lat": 29.1083, "lng": 58.3583},
    "زاهدان": {"lat": 29.4963, "lng": 60.8629},
    "زابل": {"lat": 31.0314, "lng": 61.4914},
    "ایرانشهر": {"lat": 27.2025, "lng": 60.6847},
    "چابهار": {"lat": 25.2919, "lng": 60.6433},
    "ارومیه": {"lat": 37.5527, "lng": 45.0761},
    "خوی": {"lat": 38.5503, "lng": 44.9519},
    "میاندوآب": {"lat": 36.9667, "lng": 46.1000},
    "مهاباد": {"lat": 36.7631, "lng": 45.7219},
    "بوکان": {"lat": 36.5208, "lng": 46.2092},
    "کرمانشاه": {"lat": 34.3142, "lng": 47.0650},
    "islamabadgharb": {"lat": 34.1094, "lng": 46.5292},
    "اسلامآبادغرب": {"lat": 34.1094, "lng": 46.5292},
    "سرپلذهاب": {"lat": 34.4614, "lng": 45.8625},
    "خرمآباد": {"lat": 33.4878, "lng": 48.3538},
    "بروجرد": {"lat": 33.8972, "lng": 48.7514},
    "دورود": {"lat": 33.4939, "lng": 49.0778},
    "کوهدشت": {"lat": 33.5342, "lng": 47.6081},
    "همدان": {"lat": 34.7984, "lng": 48.5146},
    "ملایر": {"lat": 34.2981, "lng": 48.8242},
    "نهاوند": {"lat": 34.1886, "lng": 48.3756},
    "یزد": {"lat": 31.8974, "lng": 54.3569},
    "میبد": {"lat": 32.2272, "lng": 54.0092},
    "اردکان": {"lat": 32.3100, "lng": 54.0175},
    "سنندج": {"lat": 35.3113, "lng": 46.9959},
    "سقز": {"lat": 36.2497, "lng": 46.2736},
    "مریوان": {"lat": 35.5261, "lng": 46.1758},
    "قم": {"lat": 34.6416, "lng": 50.8746},
    "قزوین": {"lat": 36.2687, "lng": 50.0041},
    "الوند": {"lat": 36.1892, "lng": 50.0639},
    "تاکستان": {"lat": 36.0694, "lng": 49.6958},
    "گرگان": {"lat": 36.8456, "lng": 54.4393},
    "گنبدکاووس": {"lat": 37.2500, "lng": 55.1667},
    "اردبیل": {"lat": 38.2514, "lng": 48.2973},
    "پارسآباد": {"lat": 39.6483, "lng": 47.9172},
    "مشگینشهر": {"lat": 38.3986, "lng": 47.6814},
    "اراک": {"lat": 34.0954, "lng": 49.6913},
    "ساوه": {"lat": 35.0214, "lng": 50.3567},
    "خمین": {"lat": 33.6425, "lng": 50.0789},
    "زنجان": {"lat": 36.6736, "lng": 48.4787},
    "ابهر": {"lat": 36.1464, "lng": 49.2178},
    "بوشهر": {"lat": 28.9234, "lng": 50.8203},
    "برازجان": {"lat": 29.2667, "lng": 51.2158},
    "کنگان": {"lat": 27.8342, "lng": 52.0628},
    "شهرکرد": {"lat": 32.3256, "lng": 50.8644},
    "بروجن": {"lat": 31.9683, "lng": 51.2900},
    "بیرجند": {"lat": 32.8663, "lng": 59.2211},
    "بجنورد": {"lat": 37.4761, "lng": 57.3317},
    "شیروان": {"lat": 37.3967, "lng": 57.9294},
    "یاسوج": {"lat": 30.6691, "lng": 51.5878},
    "دوگنبدان": {"lat": 30.3586, "lng": 50.7981},
    "بندرعباس": {"lat": 27.1833, "lng": 56.2667},
    "میناب": {"lat": 27.1464, "lng": 57.0797},
    "سمنان": {"lat": 35.5722, "lng": 53.3960},
    "شاهرود": {"lat": 36.4181, "lng": 54.9761},
    "ایلام": {"lat": 33.6374, "lng": 46.4227},
}

# مختصات مرکز استان‌ها به عنوان fallback
IRAN_PROVINCE_COORDINATES: dict[str, dict[str, float]] = {
    "تهران": {"lat": 35.6892, "lng": 51.3890},
    "اصفهان": {"lat": 32.6546, "lng": 51.6680},
    "خراسانرضوی": {"lat": 36.2972, "lng": 59.6067},
    "آذربایجانشرقی": {"lat": 38.0962, "lng": 46.2738},
    "فارس": {"lat": 29.5918, "lng": 52.5837},
    "خوزستان": {"lat": 31.3183, "lng": 48.6706},
    "مازندران": {"lat": 36.5633, "lng": 53.0601},
    "البرز": {"lat": 35.8327, "lng": 50.9915},
    "گیلان": {"lat": 37.2808, "lng": 49.5831},
    "کرمان": {"lat": 30.2839, "lng": 57.0834},
    "سیستانوبلوچستان": {"lat": 29.4963, "lng": 60.8629},
    "آذربایجانغربی": {"lat": 37.5527, "lng": 45.0761},
    "کرمانشاه": {"lat": 34.3142, "lng": 47.0650},
    "لرستان": {"lat": 33.4878, "lng": 48.3538},
    "همدان": {"lat": 34.7984, "lng": 48.5146},
    "یزد": {"lat": 31.8974, "lng": 54.3569},
    "کردستان": {"lat": 35.3113, "lng": 46.9959},
    "قم": {"lat": 34.6416, "lng": 50.8746},
    "قزوین": {"lat": 36.2687, "lng": 50.0041},
    "گلستان": {"lat": 36.8456, "lng": 54.4393},
    "ardabil": {"lat": 38.2514, "lng": 48.2973},
    "اردبیل": {"lat": 38.2514, "lng": 48.2973},
    "مرکزی": {"lat": 34.0954, "lng": 49.6913},
    "زنجان": {"lat": 36.6736, "lng": 48.4787},
    "بوشهر": {"lat": 28.9234, "lng": 50.8203},
    "چهارمحالوبختیاری": {"lat": 32.3256, "lng": 50.8644},
    "خراسانجنوبی": {"lat": 32.8663, "lng": 59.2211},
    "خراسانشمالی": {"lat": 37.4761, "lng": 57.3317},
    "کهگیلویهوبویراحمد": {"lat": 30.6691, "lng": 51.5878},
    "هرمزگان": {"lat": 27.1833, "lng": 56.2667},
    "سمنان": {"lat": 35.5722, "lng": 53.3960},
    "ایلام": {"lat": 33.6374, "lng": 46.4227},
}


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
        # Selectors that only resolved once the ``:visible`` filter was dropped.
        self._hidden_selector_fallbacks: set[str] = set()

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if value is None:
            return ""
        normalized = str(value).strip().lower()
        replacements = {
            "ي": "ی",
            # UTCMS returns province names with the Arabic alef maksura, e.g.
            # "خراسان رضوى" / "آذربایجان شرقى", while operators type "رضوی".
            "ى": "ی",
            "ك": "ک",
            "‌": "",
            "\u200f": "",
            "\u200e": "",
            "ۀ": "ه",
            "ة": "ه",
            "أ": "ا",
            "إ": "ا",
        }
        for source, target in replacements.items():
            normalized = normalized.replace(source, target)
        return "".join(normalized.split())

    @staticmethod
    def _build_manual_address(location_data: dict[str, Any]) -> str | None:
        """Build fallback text only from a caller-provided, non-placeholder address."""
        address = str(location_data.get("address") or "").strip()
        if len(address) < 2 or address.lower() in {"-", "null", "none", "x", ":x:", ":x"}:
            return None
        parts = [
            str(location_data.get(key) or "").strip()
            for key in ("province", "city", "address")
            if str(location_data.get(key) or "").strip()
        ]
        return "، ".join(parts) or None

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

    async def _resolve_selector(self, selector: str) -> str | None:
        """بازگرداندن شکل قابل‌کوئری یک selector با اولویت نسخه visible.

        UTCMS چند مسیر مشروع برای پنهان کردن کنترل‌ها دارد: پنل pill غیرفعال،
        جایگزینی select2 و wrapper های قالب.  یک ``select`` پنهان اما attached
        همچنان فهرست گزینه‌های معتبر را نگه می‌دارد و همچنان رویداد ``change``
        را منتشر می‌کند؛ پس اگر هیچ تطابق visible نبود، بازگشت به selector خام
        جریان متنی را حفظ می‌کند -- جایی که فیلتر ``:visible`` تنها یک dropdown
        خالی گزارش می‌کرد (ریشه شکست «گزینه‌های استان بارگذاری نشدند»).
        """
        if not selector:
            return None

        visible_selector = self._make_visible_selector(selector)
        try:
            if await self.page.query_selector(visible_selector):
                return visible_selector
        except Exception:
            logger.debug("selector_visible_probe_failed", exc_info=True)

        try:
            if await self.page.query_selector(selector):
                if selector not in self._hidden_selector_fallbacks:
                    self._hidden_selector_fallbacks.add(selector)
                    logger.info(
                        "location_selector_hidden_fallback",
                        extra={"extra_fields": {"selector": selector}},
                    )
                return selector
        except Exception:
            logger.debug("selector_attached_probe_failed", exc_info=True)

        return None

    async def _fill_input_like(self, selector: str, value: str, visible: bool = True) -> bool:
        if not value:
            return False

        if visible:
            resolved = await self._resolve_selector(selector)
            if resolved is None:
                return False
            target_selector = resolved
        else:
            target_selector = selector

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
            logger.warning("location_selector_error", exc_info=True)

        if not visible or target_selector == selector:
            # For hidden inputs, do not call page.fill (it will hang waiting for visibility)
            return False

        # 2. Fallback to Playwright's standard fill
        try:
            await self.page.fill(target_selector, value)
            await self.page.eval_on_selector(
                target_selector,
                "el => { el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('input').trigger('change').trigger('keyup'); } }",
            )
            return True
        except Exception:
            logger.warning("location_selector_error", exc_info=True)

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
            logger.warning("location_selector_error", exc_info=True)

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
            await asyncio.sleep(0.05)
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
            logger.warning("location_selector_error", exc_info=True)

        # Try clicking the tab
        try:
            await self.page.click(tab_selector, timeout=3000)
            await asyncio.sleep(0.1)
        except Exception:
            logger.warning("location_selector_error", exc_info=True)

        # Force activate via JS if click didn't work
        try:
            await self.page.evaluate(
                """([tabId, paneId]) => {
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
                [tab_id, pane_id],
            )
            await asyncio.sleep(0.06)
        except Exception:
            logger.warning("location_selector_error", exc_info=True)

    async def _read_select_options(self, selector: str) -> list[dict[str, str]]:
        try:
            resolved = await self._resolve_selector(selector)
            if resolved is None:
                return []
            option_parts = [f"{part.strip()} option" for part in resolved.split(",") if part.strip()]
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
        timeout_ms: int = 3000,
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
            await asyncio.sleep(0.05)
        return False

    async def _fetch_utcms_records(self, url: str) -> list[dict[str, Any]]:
        """واکشی مستقیم رکوردهای مرجع UTCMS از همان endpoint خود سامانه.

        درخواست از داخل صفحه (same-origin fetch) اجرا می‌شود تا از همان نشست
        احراز هویت و همان مسیر bridge استفاده کند.  هیچ داده‌ای ساخته نمی‌شود؛
        فقط پاسخ خود UTCMS خوانده می‌شود.
        """
        try:
            payload = await self.page.evaluate(
                """async (url) => {
                    try {
                        const response = await fetch(url, {
                            headers: { 'X-Requested-With': 'XMLHttpRequest' },
                            credentials: 'same-origin',
                        });
                        if (!response.ok) return { error: 'HTTP ' + response.status };
                        const text = await response.text();
                        try {
                            return JSON.parse(text);
                        } catch (parseError) {
                            return { error: 'unparsable' };
                        }
                    } catch (fetchError) {
                        return { error: String(fetchError).slice(0, 160) };
                    }
                }""",
                url,
            )
        except Exception:
            logger.warning("utcms_reference_fetch_failed", extra={"extra_fields": {"url": url}}, exc_info=True)
            return []

        if not isinstance(payload, dict):
            return []
        if payload.get("error"):
            logger.warning(
                "utcms_reference_fetch_rejected",
                extra={"extra_fields": {"url": url, "error": payload.get("error")}},
            )
            return []
        if payload.get("resultCode") not in {0, 200, "0", "200"}:
            logger.warning(
                "utcms_reference_fetch_result_code",
                extra={"extra_fields": {"url": url, "result_code": payload.get("resultCode")}},
            )
            return []

        records = payload.get("obj")
        if not isinstance(records, list):
            return []
        return [record for record in records if isinstance(record, dict)]

    async def _backfill_select_options(self, selector: str, records: list[dict[str, Any]]) -> int:
        """بازسازی گزینه‌های یک select از رکوردهای واقعی UTCMS.

        هندلر خود سامانه (``fillStates``) پاسخ ``application/json`` را روی
        envelope پیمایش می‌کند و سه گزینه ``undefined`` می‌سازد و گزینه‌های
        واقعی را هم پاک می‌کند.  این متد همان select را با ``id``/``name``
        واقعی بازنویسی می‌کند تا مقدار ارسالی به سامانه معتبر باشد.
        """
        pairs = [
            {"value": str(record.get("id") or "").strip(), "text": str(record.get("name") or "").strip()}
            for record in records
        ]
        pairs = [pair for pair in pairs if pair["value"] and pair["text"]]
        if not pairs:
            return 0

        resolved = await self._resolve_selector(selector)
        if resolved is None:
            return 0

        try:
            applied = await self.page.eval_on_selector(
                resolved,
                """(el, options) => {
                    const previous = el.value;
                    el.innerHTML = '';
                    const placeholder = document.createElement('option');
                    placeholder.value = '';
                    placeholder.textContent = 'انتخاب کنید';
                    el.appendChild(placeholder);
                    for (const option of options) {
                        const node = document.createElement('option');
                        node.value = option.value;
                        node.textContent = option.text;
                        el.appendChild(node);
                    }
                    if (previous && Array.from(el.options).some(o => o.value === previous)) {
                        el.value = previous;
                    }
                    return el.options.length - 1;
                }""",
                pairs,
            )
        except Exception:
            logger.warning("location_option_backfill_failed", extra={"extra_fields": {"selector": selector}})
            return 0

        count = int(applied or 0)
        logger.info(
            "location_options_backfilled",
            extra={"extra_fields": {"selector": selector, "count": count}},
        )
        return count

    async def _ensure_province_options(self, selectors: list[str]) -> bool:
        """اطمینان از وجود گزینه‌های واقعی استان، در صورت نیاز با backfill."""
        if await self._wait_for_select_options(selectors, min_real_options=1, timeout_ms=4000):
            return True

        records = await self._fetch_utcms_records("/Barname/Document/FillProvinces")
        if not records:
            return False
        for selector in selectors:
            if await self._backfill_select_options(selector, records):
                return True
        return False

    async def _ensure_city_options(self, selectors: list[str], state_id: str) -> bool:
        """اطمینان از وجود گزینه‌های واقعی شهر برای استان انتخاب‌شده."""
        if await self._wait_for_select_options(selectors, min_real_options=1, timeout_ms=5000):
            return True
        if not state_id:
            return False

        records = await self._fetch_utcms_records(f"/Barname/Document/FillCities?StateId={state_id}")
        if not records:
            return False
        for selector in selectors:
            if await self._backfill_select_options(selector, records):
                return True
        return False

    async def _reapply_option_value(self, selector: str, value: str) -> str:
        """بازنشانی مقدار یک select بدون انتشار change (برای جلوگیری از حلقه AJAX)."""
        resolved = await self._resolve_selector(selector)
        if resolved is None:
            return "detached"
        try:
            return str(
                await self.page.eval_on_selector(
                    resolved,
                    """(el, wanted) => {
                        const value = String(wanted ?? '');
                        if (!Array.from(el.options || []).some(o => (o.getAttribute('value') || '') === value)) {
                            return 'missing';
                        }
                        el.value = value;
                        return el.value === value ? 'ok' : 'failed';
                    }""",
                    value,
                )
                or "failed"
            )
        except Exception:
            logger.warning("location_option_reapply_failed", extra={"extra_fields": {"selector": selector}})
            return "failed"

    async def _hold_select_value(
        self,
        selector: str,
        value: str,
        *,
        settle_ms: int = 3000,
        refill: Callable[[], Awaitable[bool]] | None = None,
    ) -> bool:
        """نگه‌داشتن مقدار انتخاب‌شده تا زمانی که AJAX خود سامانه آرام بگیرد.

        هندلر ``change`` روی ``#ddStateSource`` درخواست ``FillCities`` می‌فرستد و
        در پاسخ، ``#ddCitySource`` را ``empty()`` می‌کند؛ پاسخی که ثانیه‌ها بعد از
        انتخاب ما می‌رسد و انتخاب شهر را پاک می‌کند.  این متد در بازه‌ی مشخصی
        مقدار را پایش می‌کند و در صورت پاک‌شدن دوباره اعمالش می‌کند -- بدون
        انتشار ``change`` تا حلقه‌ی AJAX تکرار نشود.
        """
        if not value:
            return False

        loop = asyncio.get_running_loop()
        deadline = loop.time() + max(0.5, settle_ms / 1000)
        reapplied = 0
        while loop.time() < deadline:
            await asyncio.sleep(0.25)
            current = await self._read_selected_option(selector)
            if str(current.get("value") or "").strip() == value:
                continue
            outcome = await self._reapply_option_value(selector, value)
            if outcome == "missing" and refill is not None:
                if await refill():
                    outcome = await self._reapply_option_value(selector, value)
            if outcome == "ok":
                reapplied += 1
                continue
            logger.warning(
                "location_selection_hold_failed",
                extra={"extra_fields": {"selector": selector, "value": value, "outcome": outcome}},
            )
            return False

        final = await self._read_selected_option(selector)
        held = str(final.get("value") or "").strip() == value
        if reapplied:
            logger.info(
                "location_selection_reasserted",
                extra={"extra_fields": {"selector": selector, "value": value, "times": reapplied, "held": held}},
            )
        return held

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

    async def _fetch_reverse_geocode(self, lat: float, lng: float) -> dict[str, Any] | None:
        try:
            return await self.page.evaluate(
                """async ([lat, lng]) => {
                    try {
                        const response = await fetch('/Barname/Document/RevereseMap?lat=' + lat + '&lon=' + lng);
                        if (response.ok) {
                            const data = await response.json();
                            return data.obj;
                        }
                    } catch (e) {
                        return null;
                    }
                    return null;
                }""",
                [lat, lng],
            )
        except Exception:
            return None

    async def select_location(self, location_data: dict[str, Any], origin: bool = True) -> dict[str, Any]:
        """
        انتخاب مکان با اولویت حالت user_text:
        در حالت user_text منحصراً از فیلدهای مستقیم متنی UTCMS (استان، شهر، آدرس) استفاده می‌شود.
        هیچ‌گونه نقشه، مختصات یا ژئوکدینگ اجرا نخواهد شد.
        """
        prefix = "Origin" if origin else "Destination"
        location_mode = "user_text"

        logger.info(
            "location_selection_started",
            extra={"extra_fields": {"prefix": prefix, "location_mode": location_mode, "location_data": location_data}},
        )

        # 1. Ensure the correct pill is active
        await self._ensure_location_tab_active(prefix)
        await asyncio.sleep(0.06)

        # ── جریان اجباری user_text ─────────────────────────────────────────────
        result = await self._try_utcms_direct_fill(location_data, prefix)
        if result.get("success"):
            logger.info(
                "utcms_user_text_location_selection_succeeded",
                extra={"extra_fields": {"prefix": prefix, "result": result}},
            )
            return result

        error_msg = result.get("error") or f"انتخاب مکان متنی ({prefix}) ناموفق بود"
        logger.error(
            "utcms_user_text_location_selection_failed",
            extra={"extra_fields": {"prefix": prefix, "error": error_msg, "location_data": location_data}},
        )
        raise LocationSelectionError(f"خطای انتخاب مکان ({prefix}): {error_msg}")

    async def _read_element_value(self, selector: str) -> str:
        """بازخوانی مقدار متنی یک input یا textarea از DOM."""
        try:
            resolved = await self._resolve_selector(selector)
            if resolved is None:
                return ""
            val = await self.page.eval_on_selector(
                resolved,
                "el => (el.value || el.innerText || el.textContent || '').trim()",
            )
            return str(val or "").strip()
        except Exception:
            return ""

    async def _read_selected_option(self, selector: str) -> dict[str, str]:
        """بازخوانی مقدار و متن گزینه انتخاب‌شده در یک select از DOM."""
        try:
            resolved = await self._resolve_selector(selector)
            if resolved is None:
                return {"value": "", "text": ""}
            return await self.page.eval_on_selector(
                resolved,
                """el => {
                    const opt = el.selectedOptions ? el.selectedOptions[0] : null;
                    return {
                        value: (el.value || '').trim(),
                        text: opt ? (opt.text || opt.innerText || '').trim() : ''
                    };
                }""",
            )
        except Exception:
            return {"value": "", "text": ""}

    async def _try_utcms_direct_fill(
        self,
        location_data: dict[str, Any],
        prefix: str,
    ) -> dict[str, Any]:
        """
        ترتیب استاندارد و اجباری انتخاب مکان در حالت user_text:
        ۱. فعال‌سازی تب
        ۲. انتخاب استان
        ۳. انتظار برای لود AJAX شهرها
        ۴. انتخاب شهر (تطابق یکتا، بدون حدس اولین گزینه)
        ۵. Read-back شهر (مقدار و برچسب)
        ۶. پر کردن آدرس متنی
        ۷. Read-back آدرس متنی
        ۸. بررسی خطاهای اعتبارسنجی
        ۹. بازگرداندن نتیجه مطمئن
        """
        is_origin = prefix in {"Origin", "Source", "origin", "source"}
        utcms = self._get_utcms_selectors(is_origin)
        province = (location_data.get("province") or "").strip()
        city = (location_data.get("city") or "").strip()
        district = (location_data.get("district") or "").strip()
        address = (location_data.get("address") or "").strip()

        placeholder_values = {"-", "null", "none", "x", ":x:", ":x"}
        if (
            len(province) < 2
            or len(city) < 2
            or len(address) < 2
            or province.lower() in placeholder_values
            or city.lower() in placeholder_values
            or address.lower() in placeholder_values
        ):
            return {
                "success": False,
                "method": "utcms_direct_text",
                "error": f"اطلاعات مسیر ناقص است ({prefix}): استان='{province}', شهر='{city}', آدرس='{address}'",
            }

        try:
            # ۱. اطمینان از فعال بودن تب
            await self._ensure_location_tab_active(prefix)

            # ۲. انتظار و بارگذاری گزینه‌های استان (با backfill از خود UTCMS)
            province_ready = await self._ensure_province_options(utcms["province"])
            if not province_ready:
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"گزینه‌های استان ({prefix}) در بازه زمانی تعیین‌شده بارگذاری نشدند",
                }

            # انتخاب استان
            province_selector = await self._select_from_options_with_selector(utcms["province"], province)
            if not province_selector:
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"انتخاب استان '{province}' در فرم ({prefix}) ناموفق بود",
                }

            # Read-back استان
            province_readback = await self._read_selected_option(province_selector)
            norm_prov_target = self._normalize_text(province)
            norm_prov_read = self._normalize_text(province_readback.get("text", ""))
            if not province_readback.get("value") or (
                norm_prov_target not in norm_prov_read and norm_prov_read not in norm_prov_target
            ):
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"عدم تطابق Read-back استان ({prefix}): مورد انتظار='{province}'، بازخوانی‌شده='{province_readback.get('text')}'",
                }

            # ۳. انتظار برای بارگذاری AJAX گزینه‌های شهر بعد از انتخاب استان
            city_ready = await self._ensure_city_options(
                utcms["city"],
                str(province_readback.get("value") or "").strip(),
            )
            if not city_ready:
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"گزینه‌های شهر برای استان '{province}' ({prefix}) پس از درخواست AJAX بارگذاری نشدند",
                }

            # ۴. انتخاب شهر بر اساس تطابق یکتا (بدون حدس اولین گزینه)
            city_selector = await self._select_from_options_with_selector(utcms["city"], city)
            if not city_selector:
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"شهر '{city}' در میان گزینه‌های استان '{province}' ({prefix}) یافت نشد",
                }

            city_readback = await self._read_selected_option(city_selector)
            province_value = str(province_readback.get("value") or "").strip()
            city_value = str(city_readback.get("value") or "").strip()

            async def _refill_cities() -> bool:
                return await self._ensure_city_options([city_selector], province_value)

            # ۴.۵ تثبیت انتخاب شهر در برابر AJAX پاسخ FillCities سامانه
            if city_value:
                await self._hold_select_value(city_selector, city_value, settle_ms=1500, refill=_refill_cities)

            # ۵. Read-back شهر (مقدار و برچسب).  _hold_select_value performs
            # the final value stability check while this read-back preserves
            # the exact label returned by the selection.
            norm_city_target = self._normalize_text(city)
            norm_city_read = self._normalize_text(city_readback.get("text", ""))
            if not city_readback.get("value") or (
                norm_city_target not in norm_city_read and norm_city_read not in norm_city_target
            ):
                if city_value:
                    await self._reapply_option_value(city_selector, city_value)
                    await asyncio.sleep(0.2)
                    city_readback = await self._read_selected_option(city_selector)
                    norm_city_read = self._normalize_text(city_readback.get("text", ""))

                if not city_readback.get("value") or (
                    norm_city_target not in norm_city_read and norm_city_read not in norm_city_target
                ):
                    return {
                        "success": False,
                        "method": "utcms_direct_text",
                        "error": f"عدم تطابق Read-back شهر ({prefix}): مورد انتظار='{city}'، بازخوانی‌شده='{city_readback.get('text')}'",
                    }

            # ۶. پر کردن آدرس متنی در textarea
            addr_filled = False
            address_selector = ""
            for sel in utcms["address"]:
                filled = await self._fill_input_like(sel, address)
                if filled:
                    addr_filled = True
                    address_selector = sel
                    break

            if not addr_filled:
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"درج آدرس در فیلد متنی ({prefix}) ناموفق بود",
                }

            # ۷. Read-back آدرس متنی از DOM
            addr_readback = await self._read_element_value(address_selector)
            if not addr_readback or self._normalize_text(addr_readback) != self._normalize_text(address):
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"عدم تطابق Read-back آدرس ({prefix}): مورد انتظار='{address}'، بازخوانی‌شده='{addr_readback}'",
                }

            # ۷.۵ تثبیت انتخاب استان/شهر تا پاسخ AJAX خود سامانه آن را پاک نکند
            province_value = str(province_readback.get("value") or "").strip()
            city_value = str(city_readback.get("value") or "").strip()

            async def _refill_cities() -> bool:
                return await self._ensure_city_options([city_selector], province_value)

            if not await self._hold_select_value(province_selector, province_value):
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"مقدار استان ({prefix}) پس از پاسخ AJAX سامانه پایدار نماند",
                }
            if not await self._hold_select_value(city_selector, city_value, refill=_refill_cities):
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"مقدار شهر ({prefix}) پس از پاسخ AJAX سامانه پایدار نماند",
                }

            # ۸. بررسی خطاهای احتمالی فرم
            pane_id = "#pills-5" if is_origin else "#pills-6"
            has_error = await self.page.eval_on_selector(
                pane_id,
                """el => {
                    const err = el.querySelector('.text-danger:not(:empty), .field-validation-error:not(:empty)');
                    return err ? err.innerText.trim() : null;
                }""",
            )
            if has_error:
                return {
                    "success": False,
                    "method": "utcms_direct_text",
                    "error": f"خطای اعتبارسنجی فرم ({prefix}): {has_error}",
                }

            return {
                "success": True,
                "method": "utcms_direct_text",
                "route_source": "user_text",
                "coordinates_used": False,
                "province": province,
                "city": city,
                "district": district,
                "address": address,
                "readback": {
                    "province_text": province_readback.get("text"),
                    "province_value": province_readback.get("value"),
                    "city_text": city_readback.get("text"),
                    "city_value": city_readback.get("value"),
                    "address": addr_readback,
                },
            }

        except Exception as exc:
            return {"success": False, "method": "utcms_direct_text", "error": str(exc)}

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
        if self._build_manual_address(location_data) is None:
            return {
                "success": False,
                "method": "explicit_coords",
                "error": "آدرس متنی واقعی برای fallback مختصات وارد نشده است",
            }

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
                [lat, lng, prefix, province, city, address],
            )

            # 2. تزریق به فیلدهای مخفی DOM به عنوان پشتیبان
            await self._fill_coordinate_hidden_fields(lat, lng, prefix)
            await self._inject_coordinates_via_js(lat, lng, prefix)

            # 3. اگر متد بومی اجرا شد، منتظر پر شدن فیلدهای آدرس می‌شویم
            if native_called:
                addr_selector = "#txtAddressSource" if prefix == "Origin" else "#txtAddressDest"
                _state_selector = "#ddStateSource" if prefix == "Origin" else "#ddStateDest"

                # حداکثر 3 ثانیه برای پاسخ دهی متد بومی صبر می‌کنیم
                for _ in range(15):
                    try:
                        addr_val = await self.page.locator(addr_selector).input_value()
                        # In map mode, the province dropdown might be hidden and empty, so we only check address field
                        if addr_val:
                            logger.info(f"Native reverse mapping successfully populated fields for {prefix}.")
                            return {
                                "success": True,
                                "method": "explicit_coordinates_native_reverse_mapped",
                                "coordinates": {"lat": lat, "lng": lng},
                            }
                    except Exception:
                        logger.warning("location_selector_error", exc_info=True)
                    await asyncio.sleep(0.05)

            # 4. اگر فیلدها پر نشدند (مثلا به خاطر خطای سرویس نقشه سایت)، به صورت دستی آدرس را پر می‌کنیم
            full_address = self._build_manual_address(location_data)
            if full_address is None:
                return {
                    "success": False,
                    "method": "explicit_coords",
                    "error": "آدرس متنی واقعی برای fallback مختصات وارد نشده است",
                }
            addr_selector = "#txtAddressSource" if prefix == "Origin" else "#txtAddressDest"

            logger.warning(
                f"Native reverse mapping did not populate fields for {prefix}. Attempting manual address field filling: {full_address}"
            )

            _addr_filled = False
            address_selectors = [
                addr_selector,
                f"#txtAddress{prefix}FromMap",
                f"#txtAddress{prefix}",
            ]
            for selector in address_selectors:
                try:
                    if await self._fill_input_like(selector, full_address, visible=False):
                        _addr_filled = True
                except Exception:
                    continue

            # چک می‌کنیم که آیا اکنون مقدار دارد
            addr_val = ""
            try:
                addr_val = await self.page.locator(addr_selector).input_value()
            except Exception:
                logger.warning("location_selector_error", exc_info=True)

            if addr_val:
                logger.info(f"Successfully populated location inputs for {prefix} via manual address injection.")
                return {
                    "success": True,
                    "method": "explicit_coordinates_manual_address_injection",
                    "coordinates": {"lat": lat, "lng": lng},
                }

            # ۵. اگر ورودی آدرس متنی هم پر نشد، به عنوان آخرین راهکار سراغ دراپ‌دان آبشاری می‌رویم
            logger.warning(
                f"Manual address injection did not populate fields for {prefix}. Falling back to manual dropdown selection."
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
                "error": "عدم موفقیت در مقداردهی بومی، دستی و آبشاری فیلدهای مکان",
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
        if self._build_manual_address(location_data) is None:
            return {
                "success": False,
                "method": "map",
                "error": "آدرس متنی واقعی برای انتخاب مکان وارد نشده است",
            }

        # اول پنل صحیح را فعال کنیم، سپس نقشه را تشخیص دهیم
        await self._ensure_location_tab_active(prefix)

        # انتظار برای نمایان شدن کانتینر نقشه در DOM
        map_selector = "#MapSource" if prefix == "Origin" else "#MapDestination"
        map_visible = False
        for _ in range(30):  # حداکثر ۳ ثانیه انتظار
            if await self._is_selector_visible(map_selector):
                map_visible = True
                break
            await asyncio.sleep(0.1)

        if not map_visible:
            logger.warning(f"Map container {map_selector} not visible after tab activation. Proceeding anyway.")

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

            # ادغام کادر جستجوی نقشه به عنوان راهکار فیزیکی جایگزین
            search_input_selector = utcms.get("map_search", [None])[0] if utcms.get("map_search") else None

            selected = await self.map_controller.select_on_map(
                selector=map_selector,
                location=location,
                search_input_selector=search_input_selector,
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
                    has_changes = any(val and val != before_state.get(key) for key, val in after_state.items())
                    if has_changes:
                        break
                    await asyncio.sleep(0.05)

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
                        full_address = self._build_manual_address(location_data)
                        if full_address is None:
                            return {
                                "success": False,
                                "method": "map",
                                "error": "آدرس متنی واقعی برای fallback نقشه وارد نشده است",
                            }

                        addr_filled = False
                        for sel in utcms["address"] + self._build_formatted_selectors(
                            LocationSelectors.ADDRESS_TEMPLATES, prefix=prefix
                        ):
                            if await self._fill_input_like(sel, full_address, visible=False):
                                addr_filled = True

                        if addr_filled:
                            logger.info("Map click had no effect, but manual address injection succeeded.")
                            return {
                                "success": True,
                                "method": "map_manual_address_injection",
                                "coordinates": {"lat": lat, "lng": lng},
                                "map_type": map_type,
                            }
                        return {
                            "success": False,
                            "method": "map",
                            "error": "کلیک روی نقشه تاثیری در فرم نداشت (فیلدها تغییر نکردند)",
                        }

                    # In map mode, the province/city dropdowns might be hidden and empty, so we only check the address field
                    if not after_state.get("address"):
                        logger.warning(
                            "map_click_missing_address_falling_back",
                            extra={"extra_fields": {"prefix": prefix, "after_state": after_state}},
                        )
                        full_address = self._build_manual_address(location_data)
                        if full_address is None:
                            return {
                                "success": False,
                                "method": "map",
                                "error": "آدرس متنی واقعی برای fallback نقشه وارد نشده است",
                            }

                        addr_filled = False
                        for sel in utcms["address"] + self._build_formatted_selectors(
                            LocationSelectors.ADDRESS_TEMPLATES, prefix=prefix
                        ):
                            if await self._fill_input_like(sel, full_address, visible=False):
                                addr_filled = True

                        if addr_filled:
                            logger.info("Map click missing address, but manual address injection succeeded.")
                            return {
                                "success": True,
                                "method": "map_manual_address_injection",
                                "coordinates": {"lat": lat, "lng": lng},
                                "map_type": map_type,
                            }

                        dropdown_result = await self._try_dropdown_selection(location_data, prefix, selectors=selectors)
                        if dropdown_result["success"]:
                            return {
                                "success": True,
                                "method": "map_with_dropdown_fallback",
                                "coordinates": {"lat": lat, "lng": lng},
                                "map_type": map_type,
                            }
                        return {
                            "success": False,
                            "method": "map",
                            "error": "آدرس پس از کلیک نقشه مقداردهی نشد و فال‌بک ناموفق بود",
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
                province_tmpl = self._build_formatted_selectors(LocationSelectors.PROVINCE_TEMPLATES, prefix=prefix)
                city_tmpl = self._build_formatted_selectors(LocationSelectors.CITY_TEMPLATES, prefix=prefix)
                district_tmpl = self._build_formatted_selectors(LocationSelectors.DISTRICT_TEMPLATES, prefix=prefix)
            else:
                province_tmpl = selectors["province"]
                city_tmpl = selectors["city"]
                district_tmpl = selectors.get("district", [])

            # Merge UTCMS direct selectors at the head (highest priority)
            merged_province = self._unique_preserve_order(utcms["province"] + province_tmpl)
            merged_city = self._unique_preserve_order(utcms["city"] + city_tmpl)
            merged_district = self._unique_preserve_order(utcms["district"] + district_tmpl)

            await self._wait_for_select_options(merged_province, timeout_ms=3000)
            for selector in merged_province[:3]:
                await self._log_select_diagnostics(
                    selector, f"{prefix} province", str(location_data.get("province", ""))
                )

            province_selected = await self._select_from_options(merged_province, location_data.get("province", ""))
            if not province_selected:
                return {"success": False, "method": "dropdown", "error": "انتخاب استان با شکست مواجه شد"}

            city_options_ready = await self._wait_for_select_options(merged_city, timeout_ms=4000)
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

            await self._wait_for_select_options(merged_district, timeout_ms=2000)
            await self._select_from_options(merged_district, location_data.get("district", ""))

            # پر کردن آدرس - ابتدا UTCMS direct, سپس template
            address_selectors = self._unique_preserve_order(
                utcms["address"] + self._build_formatted_selectors(LocationSelectors.ADDRESS_TEMPLATES, prefix=prefix)
            )
            address = location_data.get("address", "")
            if not str(address or "").strip() or len(str(address).strip()) < 2:
                return {"success": False, "method": "dropdown", "error": "آدرس واقعی وارد نشده است"}
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
            await asyncio.sleep(0.16)
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
            await asyncio.sleep(0.06)
            search_input = self.page.locator("input.select2-search__field").last
            await search_input.fill(search_value, timeout=3000)
            await asyncio.sleep(0.2)
            results = self.page.locator(".select2-results__option")
            count = await results.count()
            for idx in range(count):
                option = results.nth(idx)
                text = self._normalize_text(await option.inner_text())
                target = self._normalize_text(search_value)
                if target and (target in text or text in target):
                    await option.click(timeout=3000)
                    await asyncio.sleep(0.1)
                    try:
                        await self.page.eval_on_selector(
                            select_selector,
                            "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }",
                        )
                    except Exception:
                        logger.warning("location_selector_error", exc_info=True)
                    return True
            if count > 0:
                await results.nth(0).click(timeout=3000)
                await asyncio.sleep(0.1)
                try:
                    await self.page.eval_on_selector(
                        select_selector,
                        "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }",
                    )
                except Exception:
                    logger.warning("location_selector_error", exc_info=True)
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
            await asyncio.sleep(0.05)
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

                    await asyncio.sleep(0.1)
                    await asyncio.sleep(0.2)

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
        """یافتن بهترین تطابق هوشمند و فازی بین گزینه‌های منوی کشویی"""
        if not normalized_target:
            return None

        def clean_prefix(text: str) -> str:
            for prefix in ("استان", "شهرستان", "شهر", "بخش", "دهستان", "منطقه"):
                if text.startswith(prefix):
                    text = text[len(prefix) :]
            return text

        target_clean = clean_prefix(normalized_target)

        # ۱. تطابق کامل (Exact Match)
        for option in raw_options:
            option_text = str(option.get("text") or "").strip()
            option_value = str(option.get("value") or "").strip()
            norm_text = self._normalize_text(option_text)
            norm_val = self._normalize_text(option_value)

            if norm_text == "undefined" or norm_val == "undefined" or not (norm_text or norm_val):
                continue

            if normalized_target in (norm_text, norm_val):
                return option_value or option_text

        # ۲. تطابق بعد از حذف پیشوندهای متداول مانند "استان " یا "شهرستان "
        for option in raw_options:
            option_text = str(option.get("text") or "").strip()
            option_value = str(option.get("value") or "").strip()
            norm_text = clean_prefix(self._normalize_text(option_text))
            norm_val = clean_prefix(self._normalize_text(option_value))

            if target_clean and (target_clean == norm_text or target_clean == norm_val):
                return option_value or option_text

        # ۳. تطابق عبارت فرعی (Substring Match) - فقط در صورت یکتا بودن تطابق
        matches: list[str] = []
        for option in raw_options:
            option_text = str(option.get("text") or "").strip()
            option_value = str(option.get("value") or "").strip()
            norm_text = self._normalize_text(option_text)
            norm_val = self._normalize_text(option_value)

            if norm_text == "undefined" or norm_val == "undefined" or not (norm_text or norm_val):
                continue

            if target_clean in norm_text or target_clean in norm_val or norm_text in target_clean:
                val = option_value or option_text
                if val not in matches:
                    matches.append(val)

        # در صورتی که دقیقاً یک گزینه تطابق داشته باشد آن را انتخاب می‌کنیم (عدم حدس در صورت وجود چند گزینه)
        if len(matches) == 1:
            return matches[0]

        return None

    async def _select_option_via_js(self, selector: str, value_text: str, normalized_target: str) -> bool:
        """انتخاب گزینه در یک select پنهان‌شده از طریق JS (بدون انتظار visibility).

        فقط زمانی استفاده می‌شود که هیچ تطابق ``:visible`` وجود نداشته باشد؛
        تطابق دقیقاً همان قاعده ``_find_best_option_match`` است، پس هیچ حدسی
        روی چند گزینه مبهم زده نمی‌شود.
        """
        options = await self._read_select_options(selector)
        if not options:
            return False

        target_value = self._find_best_option_match(options, normalized_target) or ""
        if not target_value:
            return False

        try:
            applied = await self.page.eval_on_selector(
                selector,
                """(el, wanted) => {
                    const value = String(wanted ?? '');
                    let matched = false;
                    for (const option of Array.from(el.options || [])) {
                        const optionValue = (option.getAttribute('value') || '').trim();
                        const optionText = (option.textContent || '').trim();
                        if (optionValue === value || optionText === value) {
                            el.value = optionValue;
                            option.selected = true;
                            matched = true;
                            break;
                        }
                    }
                    if (!matched) return false;
                    el.dispatchEvent(new Event('input', { bubbles: true }));
                    el.dispatchEvent(new Event('change', { bubbles: true }));
                    if (window.jQuery) {
                        window.jQuery(el).trigger('change');
                    }
                    return true;
                }""",
                target_value,
            )
        except Exception:
            logger.warning("location_selector_error", exc_info=True)
            return False

        if not applied:
            logger.info(
                "location_option_match_failed",
                extra={"extra_fields": {"selector": selector, "target": value_text, "mode": "hidden_js"}},
            )
        return bool(applied)

    async def _select_from_options_with_selector(self, selectors: list[str], value: str) -> str | None:
        """انتخاب گزینه و بازگرداندن همان selector موفق برای read-back دقیق."""
        if not value:
            return None

        value_text = str(value).strip()
        normalized_target = self._normalize_text(value_text)

        for selector in selectors:
            try:
                visible_selector = await self._resolve_selector(selector)
                if visible_selector is None:
                    continue
                if visible_selector == selector:
                    # Hidden but attached (collapsed pane / select2 replacement):
                    # ``page.select_option`` would block on the visibility check,
                    # so drive the native select through JS instead.
                    if await self._select_option_via_js(selector, value_text, normalized_target):
                        return selector
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
                                        logger.warning("location_selector_error", exc_info=True)

                if success:
                    try:
                        await self.page.eval_on_selector(
                            visible_selector,
                            "el => { el.dispatchEvent(new Event('change', { bubbles: true })); el.dispatchEvent(new Event('keydown', { bubbles: true })); el.dispatchEvent(new Event('keyup', { bubbles: true })); el.dispatchEvent(new Event('input', { bubbles: true })); if (window.jQuery) { window.jQuery(el).trigger('change').trigger('keydown').trigger('keyup').trigger('input'); } }",
                        )
                    except Exception:
                        logger.warning("location_selector_error", exc_info=True)
                    return selector

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

        return None

    async def _select_from_options(self, selectors: list[str], value: str) -> bool:
        """انتخاب گزینه از منوی کشویی بر اساس متن یا مقدار."""
        return bool(await self._select_from_options_with_selector(selectors, value))

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
        """تبدیل آدرس به مختصات با استفاده از جستجوی محلی و کش یا سرویس خارجی به عنوان آخرین راهکار"""
        province = str(location_data.get("province", "") or "").strip()
        city = str(location_data.get("city", "") or "").strip()
        address_text = str(location_data.get("address", "") or "").strip()

        norm_province = self._normalize_text(province)
        norm_city = self._normalize_text(city)

        # ۱. بررسی کش محلی موقت در سطح پروسس
        cache_key = f"{norm_province}:{norm_city}:{self._normalize_text(address_text)}"
        if cache_key in _geocoding_cache:
            logger.info(f"Geocoding cache hit for key: {cache_key}")
            return _geocoding_cache[cache_key]

        # ۲. جستجو در دیتابیس شهرهای محلی (سریع و آفلاین)
        if norm_city in IRAN_CITY_COORDINATES:
            coords = IRAN_CITY_COORDINATES[norm_city]
            logger.info(f"Geocoding local city hit for {city} -> {coords}")
            _geocoding_cache[cache_key] = coords
            return coords

        if norm_province in IRAN_PROVINCE_COORDINATES:
            coords = IRAN_PROVINCE_COORDINATES[norm_province]
            logger.info(f"Geocoding local province hit for {province} -> {coords}")
            _geocoding_cache[cache_key] = coords
            return coords

        # ۳. در صورت عدم یافت در آفلاین، تلاش با Nominatim با زمان انتظار کوتاه‌تر
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
                # کاهش تایم‌اوت از ۴ ثانیه به ۱.۵ ثانیه جهت جلوگیری از قفل شدن ربات
                data = await self._make_http_request(url, params=params, headers=headers, timeout=1.5)
                if data:
                    coords = {"lat": float(data[0]["lat"]), "lng": float(data[0]["lon"])}
                    _geocoding_cache[cache_key] = coords
                    logger.info(f"Geocoding Nominatim hit for candidate {candidate} -> {coords}")
                    return coords
            except Exception as e:
                logger.debug(f"Candidate geocoding failed for {candidate}: {e}")

        # اگر هیچ‌کدام کار نکرد، به جای استفاده از مختصات پیش‌فرض (تهران) خطا برگردان
        address_desc = f"استان: {province}, شهر: {city}, آدرس: {address_text}"
        logger.warning(
            "geocoding_failed_all_candidates",
            extra={"extra_fields": {"address_desc": address_desc, "candidates_count": len(candidates)}},
        )
        raise LocationSelectionError(
            f'اعتبارسنجی آدرس انجام نشد: هیچ‌کدام از روش‌های موقعیت‌یابی برای آدرس "{address_desc}" کار نکرد'
        )

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
