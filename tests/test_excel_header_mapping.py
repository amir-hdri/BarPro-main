import pytest

from scripts.register_waybills_from_excel import build_ws_payload, to_header_map
from scripts.register_waybills_web_from_excel import ReverseGeoResolver, _build_request

DESCRIPTIVE_HEADERS = [
    "ردیف",
    "پلاک ملی: دو رقم آخر پلاک\nمنطقه آزاد: کد منطقه آزاد",
    "پلاک ملی: سه رقم پلاک\nمنطقه آزاد: خالی باشد",
    "پلاک ملی: حرف پلاک\nمنطقه آزاد: دو رقم پلاک",
    "پلاک ملی: دو رقم اول پلاک\nمنطقه آزاد: پنج رقم پلاک",
    "کد ملی راننده",
    "وزن بار (تن)",
    "تعداد بار",
    "ارزش بار (ریال)",
    "نام فرستنده",
    "کد ملی فرستنده",
    "موبایل فرستنده",
    "تلفن ثابت فرستنده",
    "کد پستی فرستنده",
    "lat فرستنده",
    "long فرستنده",
    "نام گیرنده",
    "کد ملی گیرنده",
    "موبایل گیرنده",
    "تلفن گیرنده",
    "کد پستی گیرنده",
    "lat گیرنده",
    "long گیرنده",
    "کد نوع بار",
    "کد نوع بسته بندی (لیست)",
    "",
    "نام کاربری اکانت ثبت",
    "رمز عبور اکانت ثبت",
    "کرایه",
    "",
    "ارسال پیامک به فرستنده (لیست)",
    "بیمه اختیاری بار (لیست)",
]

DESCRIPTIVE_ROW = [
    "5",
    "44",
    "377",
    "ع",
    "15",
    "0080226541",
    "25",
    "5",
    "90000000",
    "مجیداحدی",
    "",
    "09100000000",
    "",
    "",
    "35.517402480000001",
    "51.360269780000003",
    "شرکت پارس بتن",
    "",
    "09120000000",
    "",
    "",
    "35.729217179999999",
    "51.051760899999998",
    "15122",
    "فله#18074",
    "",
    "0080226541",
    "Ma.6713",
    "10000000",
    "",
    "خیر",
    "خیر",
]


def test_to_header_map_matches_descriptive_plate_headers():
    header_map = to_header_map(DESCRIPTIVE_HEADERS)

    assert header_map["plate_last_two"] == 1
    assert header_map["plate_three"] == 2
    assert header_map["plate_letter"] == 3
    assert header_map["plate_first_two"] == 4


def test_ws_payload_uses_plate_values_from_descriptive_headers():
    header_map = to_header_map(DESCRIPTIVE_HEADERS)

    payload = build_ws_payload(DESCRIPTIVE_ROW, header_map, serial_seed=123456)

    assert payload["bol"]["PlaqueID"] == "1537744"
    assert payload["bol"]["PlaqueSN"] == 44
    assert payload["bol"]["PlaqueType"] == "ع"


@pytest.mark.asyncio
async def test_web_payload_uses_plate_values_from_descriptive_headers():
    header_map = to_header_map(DESCRIPTIVE_HEADERS)
    geo = ReverseGeoResolver(enabled=False)

    try:
        _, excerpt, _ = await _build_request(
            row=DESCRIPTIVE_ROW,
            header_map=header_map,
            operation_mode="safe",
            login_url="https://barname.utcms.ir/Barname/Account/Login",
            include_auth=True,
            geo_resolver=geo,
            default_province="اصفهان",
            default_city="اصفهان",
        )
    finally:
        await geo.close()

    assert excerpt["plate"] == "15ع37744"
