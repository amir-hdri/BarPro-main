# GPS Pipeline Remediation — 2026-09-27

راستی‌آزمایی ممیزی + پیاده‌سازی فازهای P0/P1. معیار Release همچنان E2E واقعی
`Map → FakeTraveler → Android → UTCMS → Readback` است؛ این سند دقیقاً مشخص می‌کند
چه چیزی اثبات شد، چه چیزی کدی اصلاح شد، و چه چیزی همچنان نیازمند canary زنده است.

## 1. نتیجه راستی‌آزمایی (کد واقعی، نه حدس)

| # ممیزی | ادعا | نتیجه بررسی |
|---|---|---|
| 1. P0 اتصال Fake GPS | `/shipping/start` و `/finish` مختصات HTTP را مستقیم به UTCMS می‌دهند؛ `TravelEngine`/`build_gps_provider`/`AndroidShippingController` در مسیر نیستند | ✅ تأیید شد (`app/api/routes/shipping_gps.py:204-338`) |
| 2. P0 `/step` = 410 | عمداً غیرفعال | ✅ تأیید شد؛ تصمیم ایمنی درست، حفظ شد |
| 3. P0 چندگانگی Route | `distance_service` / `gps_shipping_manager` (1.25 و 65) / `waybill_map` (haversine خام) / `travel/route` جدا هستند | ✅ تأیید شد |
| 4. P0 interpolation خطی | `interpolate_waypoints` خط مستقیم A→B می‌سازد | ✅ تأیید شد |
| 5. P0 TravelEngine orphan | منطق consistency خوب ولی استفاده‌نشده | ✅ تأیید شد |
| 6. P0 Provider ناقص | `AndroidFakeGpsProvider` گیت 5 متری دارد ولی observer تولیدی ندارد (`There is no bundled observer yet`) | ✅ تأیید شد |
| 7. P0 نبود Observer | دقیقاً همان gap | ✅ تأیید شد |
| 8. P1 Controller وصل نیست | `AndroidShippingController.start/finish` وجود ولی در route نیست | ✅ تأیید شد |
| 9. P0 Auto-complete مبتنی بر ETA | `get_due_in_transit_jobs` و `auto_complete_shipping` بر `estimated_end_at <= now` تصمیم می‌گیرند | ✅ تأیید شد |
| 10. P1 2-point evidence | فقط Type 1 + Type 3 | ✅ تأیید شد؛ با `/step=410` سازگار، حفظ شد |
| 11. P1 باگ timestamp | `datetime.now(ZoneInfo("Asia/Tehran")).strftime(...Z)` تهران را UTC برچسب می‌زند | ✅ تأیید و اصلاح شد |
| 12. P1 Map Pin جدا شدن | `onLocationSelected` فقط در موفقیت reverse-geocode | ✅ تأیید و اصلاح شد |
| 13. P1 anchor قابل تطبیق | `_assert_route_anchor` با tolerance 0.0002 | ✅ تأیید شد؛ حفظ شد |
| 14. P1 anchor ≠ Android verification | مختصات اپراتور اثبات می‌شود نه مختصات Android | ✅ تأیید شد؛ گیت readback اضافه شد (fail-closed هنگام bridge فعال) |
| 15. P1 measured دستی | `measured_distance_km` از کاربر و required | ✅ تأیید و اصلاح شد (خودکار + override اختیاری) |
| 16. P1 Template بدون polyline | فقط lat/lng/distance/duration | ✅ تأیید و اصلاح شد (مایگریشن 040) |
| 17. Redroid state | ساب‌سیستم موجود ولی خارج از مسیر ثبت | ✅ جمع‌بندی ممیزی دقیق است؛ کد مسیر را به آن متصل کردیم ولی canary زنده همچنان لازم است |
| 18. Mock detectability | هدف پذیرش قراردادی است نه مخفی‌کردن mock | ✅ پذیرفته شد؛ `is_mock` در observation حفظ و لاگ می‌شود |

## 2. چه چیزی پیاده شد (فایل‌ها)

**P1-3 Timestamp (UTC قطعی):**
- `app/automation/gps_shipping_manager.py` — `auto_complete_shipping` اکنون `datetime.now(UTC)` می‌زند (قبلاً Tehran-labelled-as-Z).
- `app/automation/utcms_mobile_client.py` — fallback `DateTime` در `register_end_of_shipping` به UTC اصلاح + ایمپورت `UTC`.

**P0-2/P0-4 Route Authority (تک‌منبع):**
- جدید: `app/services/route_authority.py` — `resolve_route()` خروجی `{source, is_real_route, polyline, points, distance_km, duration_min/s, segments, anchor_hash, created_at, route_version}`؛ fallback صریح `haversine_fallback` که هرگز مسیر واقعی جا زده نمی‌شود.
- `app/services/distance_service.py` — به RouteAuthority delegate می‌کند (کش Redis و شکل خروجی سازگار حفظ شد).
- `app/api/routes/waybill_map.py` — `/calculate-route` اکنون snapshot کامل (polyline + source + anchor_hash) برمی‌گرداند (قبلاً haversine خام).

**Phase 5 Route Snapshot:**
- `ShippingState` — فیلدهای `route_snapshot/route_source/route_distance_km/route_duration_s/anchor_hash/coordinate_source/travel_status/travel_progress/measured_distance_km/gps_provider/provenance` (سازگار با state قدیمی).
- `init_shipping` — snapshot را best-effort فریز می‌کند؛ `ensure_route_snapshot` در start/finish برای jobهای قدیمی.

**P0-1/P0-5/P0-6 اتصال TravelEngine:**
- جدید: `app/services/shipping_travel_service.py` — `ensure_route_snapshot / build_engine_for_state / advance_travel_execution / compute_measured_distance_km / is_arrival_reached / verify_android_anchor / provider_kind_for_env`.
- `/shipping/start` — snapshot + (فقط هنگام `ANDROID_BRIDGE_ENABLED=true`) گیت readback مبدأ؛ provenance `android_verified` در غیر این صورت `operator_confirmed` (مسیر legacy بدون bridge دست‌نخورده).
- `/shipping/finish` — `measured_distance_km` اختیاری شد؛ خودکار از telemetry/مسیر + `advance_travel_execution` + گیت readback مقصد هنگام bridge فعال.
- `auto_complete_shipping` — arrival-driven: وقتی snapshot دارد و `ARRIVED` نیست → `waiting_arrival` (ETA فقط watchdog)؛ گیت readback مقصد هنگام bridge فعال؛ مسیر legacy بدون snapshot مثل قبل با ETA کار می‌کند.

**Phase 7 Observer تولیدی:**
- جدید: `app/travel/android_observer.py` — `AdbLocationObserver` روی `dumpsys location` با fail-closed کامل (disabled/device-not-ready/unparsable/stale → خطا). `parse_dump` آخرین فیکس را ترجیح می‌دهد و `is_mock` را از hintهای mock استخراج می‌کند.

**P1-4 Template polyline:**
- مایگریشن `040_add_route_template_polyline` + مدل `WaybillRouteTemplate` (5 ستون) + سرویس template که snapshot را ذخیره/بازمحاسبه می‌کند.

**P1-1/P1-2 UI:**
- `LocationMapPicker.tsx` — commit فوری مختصات به parent، سپس غنی‌سازی آدرس async؛ شکست geocode دیگر پین را نابود نمی‌کند.
- `ShippingRouteMap.tsx` — حذف inline style پیشرفت (native `<progress>`، ممیزی ui-ux-guard سبز شد)؛ ورودی فاصله اختیاری با placeholder خودکار؛ بج‌های `مسیر واقعی/تخمین` و `travel_status`؛ تایپ‌های جدید status.

**تست‌ها:**
- جدید: `tests/test_route_authority.py` (8 تست: UTC-Z، fallback صریح، roundtrip، telemetry-vs-route، engine-from-snapshot، parse_dump).
- به‌روز: `tests/test_shipping_gps_runtime.py` — تست 422 حذف و با `test_finish_derives_measured_distance_when_missing` (خودکار + سازگاری payload) جایگزین شد.
- رگرسیون سبز: 188 تست shipping/travel/route + `tsc --noEmit` + `eslint` + `ruff` + `audit-ui` همگی پاس.

## 3. چه چیزی عمداً تغییر نکرد

- `/shipping/step` همچنان 410 است — فعال‌سازی فقط بعد از اثبات contract زنده telemetry میانی.
- evidence همچنان 2-point (Type 1 + Type 3) — waypointهای نمایشی هرگز به UTCMS ارسال نمی‌شوند.
- `_assert_route_anchor` (tolerance 0.0002) حفظ شد.
- Session Vault، proxy fail-closed، lock جهش — دست‌نخورده.

## 4. گپ‌های باقی‌مانده (نیازمند canary زنده، نه کد بیشتر)

1. **E2E witness واقعی** با مختصات تست ممیزی (36.261100,50.442300 → 36.169600,50.611900): زنجیره `Map Anchor = Route Snapshot = TravelEngine endpoint = Android readback = UTCMS payload = UTCMS readback` هنوز روی Redroid زنده با `ANDROID_BRIDGE_ENABLED=true` اجرا و لاگ نشده.
2. **CI گیت‌هاب** برای کامیت فعلی مستقلاً verify نشد (workflow موجود برگردانده نشد) — باید پس از push بررسی شود.
3. **Neshan polyline واقعی** — بدون `NESHAN_API_KEY` مسیرها fallback هستند (`is_real_route=false`)؛ این by-design است ولی یعنی شبیه‌سازی جاده‌ای واقعی فقط با کلید Neshan + Redroid ممکن است.
4. **UTMCS History GPS readback** (Type 1 + samples + Type 3) پس از Finish زنده باید خوانده و ضمیمه شود.

## 5. قراردادهای عملیاتی

- Backend timestamps: همیشه UTC-Z؛ فقط UI به Asia/Tehran تبدیل می‌کند.
- `SHIPPING_GPS_PROVIDER=auto` (پیش‌فرض): bridge خاموش → `operator_anchor`؛ bridge روشن → گیت `redroid` fail-closed. `recording` فقط verification موتور است.
- Template/Job قدیمی بدون snapshot: در اولین start/finish به‌صورت best-effort snapshot می‌گیرند؛ تاریخچه بازنویسی نمی‌شود.
- `measured_source`: `operator_supplied` در برابر `route_derived` در پاسخ finish شفاف است.
