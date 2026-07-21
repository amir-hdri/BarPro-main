"""
اسکریپت ارزیابی کامل عملکرد سیستم نقشه، پارسر هوشمند آدرس و اتوماسیون ربات با داده‌های نمونه (Fake Data Scenarios)
"""

import time
from app.core.iran_locations import (
    parse_smart_address,
    get_all_provinces,
    get_cities_by_province,
    find_nearest_city_coords,
)
from app.automation.location_selector import LocationSelector


def evaluate_smart_address_parser():
    print("=" * 70)
    print("📌 سناریو ۱: ارزیابی پارس هوشمند متون سرهم و غیرساختاریافته آدرس")
    print("=" * 70)

    test_addresses = [
        "تهران، اسلامشهر، منطقه ۵، خیابان اصلی پلاک ۱۲",
        "اصفهان، خمینی‌شهر، شهرک صنعتی جی، خیابان دهم پلاک ۴",
        "گیلان، رشت، میدان شهرداری، خیابان امام خمینی",
        "خراسان رضوی، مشهد، خیابان نواب صفوی، پلاک ۲۰",
        "فارس، شیراز، خیابان زند، کوچه ۱۰",
        "البرز، کرج، فردیس، خیابان اصلی",
    ]

    for idx, raw in enumerate(test_addresses, 1):
        t0 = time.perf_counter()
        parsed = parse_smart_address(raw)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\n[تست {idx}] ورودی: {raw}")
        print(f"  ├─ استان شناسایی‌شده: {parsed['province']}")
        print(f"  ├─ شهر شناسایی‌شده:   {parsed['city']}")
        print(f"  ├─ منطقه:             {parsed['district']}")
        print(f"  ├─ آدرس استخراج‌شده:   {parsed['address']}")
        print(f"  ├─ مختصات پیشنهادی:   {parsed['coordinates']}")
        print(f"  └─ زمان پردازش:       {elapsed_ms:.3f} میلی‌ثانیه")

        assert parsed["province"] != "", f"استان برای {raw} یافت نشد!"
        assert parsed["city"] != "", f"شهر برای {raw} یافت نشد!"


def evaluate_reverse_geocode_fallback():
    print("\n" + "=" * 70)
    print("📌 سناریو ۲: ارزیابی تبدیل مختصات پین نقشه به آدرس (Offline Reverse Geocode)")
    print("=" * 70)

    fake_coordinates = [
        {"name": "مختصات تهران", "lat": 35.6892, "lng": 51.3890, "expected_prov": "تهران", "expected_city": "تهران"},
        {"name": "مختصات اصفهان", "lat": 32.6546, "lng": 51.6680, "expected_prov": "اصفهان", "expected_city": "اصفهان"},
        {"name": "مختصات شیراز", "lat": 29.5918, "lng": 52.5837, "expected_prov": "فارس", "expected_city": "شیراز"},
        {"name": "مختصات تبریز", "lat": 38.0962, "lng": 46.2738, "expected_prov": "آذربایجان شرقی", "expected_city": "تبریز"},
        {"name": "مختصات اهواز", "lat": 31.3183, "lng": 48.6706, "expected_prov": "خوزستان", "expected_city": "اهواز"},
    ]

    for item in fake_coordinates:
        t0 = time.perf_counter()
        match = find_nearest_city_coords(item["lat"], item["lng"])
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"\n[تست پین] {item['name']} ({item['lat']}, {item['lng']})")
        print(f"  ├─ استان انطباق یافته: {match['province']}")
        print(f"  ├─ شهر انطباق یافته:   {match['city']}")
        print(f"  └─ زمان محاسبات:      {elapsed_ms:.3f} میلی‌ثانیه")

        assert match["province"] == item["expected_prov"], f"خطا در انطباق استان برای {item['name']}"
        assert match["city"] == item["expected_city"], f"خطا در انطباق شهر برای {item['name']}"


def evaluate_bot_fuzzy_matching():
    print("\n" + "=" * 70)
    print("📌 سناریو ۳: ارزیابی هوشمندی ربات در منوی کشویی UTCMS (Fuzzy Option Matcher)")
    print("=" * 70)

    mock_selector = LocationSelector(None)

    # نمونه گزینه‌هایی که معمولاً در سامانه UTCMS دیده می‌شوند
    utcms_province_options = [
        {"text": "-- انتخاب استان --", "value": ""},
        {"text": "استان تهران", "value": "10"},
        {"text": "استان اصفهان", "value": "20"},
        {"text": "استان فارس", "value": "30"},
        {"text": "استان خراسان رضوی", "value": "40"},
        {"text": "استان آذربایجان شرقی", "value": "50"},
    ]

    utcms_city_options = [
        {"text": "-- انتخاب شهر --", "value": ""},
        {"text": "شهرستان خمینی شهر", "value": "201"},
        {"text": "شهرستان نجف آباد", "value": "202"},
        {"text": "شهر اصفهان", "value": "203"},
        {"text": "شهرستان کاشان", "value": "204"},
    ]

    test_cases = [
        {"target": "تهران", "options": utcms_province_options, "expected_val": "10"},
        {"target": "اصفهان", "options": utcms_province_options, "expected_val": "20"},
        {"target": "خراسان رضوی", "options": utcms_province_options, "expected_val": "40"},
        {"target": "خمینی شهر", "options": utcms_city_options, "expected_val": "201"},
        {"target": "خمینی‌شهر", "options": utcms_city_options, "expected_val": "201"}, # با نیم فاصله
        {"target": "نجف آباد", "options": utcms_city_options, "expected_val": "202"},
    ]

    for tc in test_cases:
        norm_target = mock_selector._normalize_text(tc["target"])
        matched_val = mock_selector._find_best_option_match(tc["options"], norm_target)

        print(f"[ورودی کاربر/ربات: '{tc['target']}']")
        print(f"  ├─ عبارت نرمال‌شده:   '{norm_target}'")
        print(f"  ├─ Option انتخاب‌شده:  '{matched_val}' (مورد انتظار: {tc['expected_val']})")
        
        status = "✅ موفق" if matched_val == tc["expected_val"] else "❌ ناموفق"
        print(f"  └─ وضعیت انطباق:       {status}")
        assert matched_val == tc["expected_val"], f"انطباق نادرست برای {tc['target']}"


if __name__ == "__main__":
    t_start = time.perf_counter()
    evaluate_smart_address_parser()
    evaluate_reverse_geocode_fallback()
    evaluate_bot_fuzzy_matching()
    total_sec = time.perf_counter() - t_start
    print("\n" + "=" * 70)
    print(f"🎉 کل ارزیابی با موفقیت ۱۰۰٪ و در مدت {total_sec:.4f} ثانیه به پایان رسید.")
    print("=" * 70)
