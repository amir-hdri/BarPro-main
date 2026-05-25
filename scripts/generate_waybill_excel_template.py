#!/usr/bin/env python3
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Iterable, List
from xml.sax.saxutils import escape


DATA_HEADERS = [
    "ردیف",
    "پلاک ملی: دو رقم آخر پلاک",
    "پلاک ملی: سه رقم پلاک",
    "پلاک ملی: حرف پلاک",
    "پلاک ملی: دو رقم اول پلاک",
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
    "آدرس فرستنده",
    "نام گیرنده",
    "کد ملی گیرنده",
    "موبایل گیرنده",
    "تلفن گیرنده",
    "کد پستی گیرنده",
    "lat گیرنده",
    "long گیرنده",
    "آدرس گیرنده",
    "کد نوع بار",
    "نام نوع بار",
    "کد نوع بسته بندی (لیست)",
    "نوع ناوگان",
    "رمز عبور راننده (فقط برای حمل)",
    "نام کاربری اکانت ثبت",
    "رمز عبور اکانت ثبت",
    "فاصله بین شروع و پایان حمل (دقیقه)",
    "تاریخ پایان حمل",
    "نام کاربری راننده (فقط برای حمل)",
    "ارسال پیامک به فرستنده (لیست)",
    "بیمه اختیاری بار (لیست)",
    "شناسه باربری",
    "ارتباط کاربر با خودرو",
]

SAMPLE_ROW = [
    "1",
    "84",
    "819",
    "ع",
    "39",
    "6540001371",
    "8",
    "5",
    "25000000",
    "شرکت مصالح آریا",
    "1234567891",
    "09129751456",
    "03112345678",
    "1234567891",
    "32.402286",
    "51.381595",
    "اصفهان - خیابان آزادی",
    "رضا سیار",
    "1234567891",
    "09185365222",
    "03112345678",
    "1234567891",
    "32.860259",
    "51.526419",
    "مشهد - خیابان امام رضا",
    "4618",
    "عمومی",
    "18076#18076",
    "کامیون",
    "@DriverPass1",
    "9907172420",
    "@Aaaa9000111",
    "0",
    "",
    "9907172420",
    "خیر",
    "خیر",
    "5845550",
    "1",
]

GUIDE_ROWS = [
    ["قالب استاندارد ورود بارنامه", "", "", "", ""],
    ["نکته", "مقدار", "", "", ""],
    ["محل ورود داده", "فقط شیت «ورود اطلاعات»", "", "", ""],
    ["شروع ورود", "از ردیف 3", "", "", ""],
    ["ترتیب ستون‌ها", "تغییر ندهید", "", "", ""],
    ["فرمت فایل", "xlsx", "", "", ""],
    ["ردیف نمونه", "ردیف 2 فقط نمونه معتبر است؛ می‌توانید ویرایش یا کپی کنید", "", "", ""],
    ["توصیه", "برای سازگاری کامل پروژه، همه ستون‌ها را پر کنید", "", "", ""],
    ["", "", "", "", ""],
    ["نام ستون", "وضعیت", "توضیح", "نمونه معتبر", "استفاده"],
    ["ردیف", "اختیاری", "شماره داخلی ردیف", "1", "مرتب‌سازی/خوانایی"],
    ["پلاک ملی: دو رقم آخر پلاک", "الزامی", "دو رقم سمت راست پلاک", "84", "وب + WS"],
    ["پلاک ملی: سه رقم پلاک", "الزامی", "سه رقم میانی پلاک", "819", "وب + WS"],
    ["پلاک ملی: حرف پلاک", "الزامی", "حرف پلاک", "ع", "وب + WS"],
    ["پلاک ملی: دو رقم اول پلاک", "الزامی", "دو رقم سمت چپ پلاک", "39", "وب + WS"],
    ["کد ملی راننده", "الزامی", "کد ملی 10 رقمی", "6540001371", "وب + WS"],
    ["وزن بار (تن)", "الزامی", "عدد مثبت؛ اعشاری مجاز", "8", "وب + WS"],
    ["تعداد بار", "الزامی", "عدد صحیح مثبت", "5", "وب + WS"],
    ["ارزش بار (ریال)", "الزامی", "عدد صحیح مثبت", "25000000", "وب + WS"],
    ["نام فرستنده", "الزامی", "نام شخص یا شرکت", "شرکت مصالح آریا", "وب + WS"],
    ["کد ملی فرستنده", "توصیه‌شده", "برای سازگاری کامل 10 رقمی پر شود", "1234567891", "WS و فرم فرستنده"],
    ["موبایل فرستنده", "الزامی", "شماره موبایل", "09129751456", "وب + WS"],
    ["تلفن ثابت فرستنده", "اختیاری", "بدون خط تیره", "03112345678", "وب + WS"],
    ["کد پستی فرستنده", "توصیه‌شده", "کد پستی 10 رقمی", "1234567891", "وب + WS"],
    ["lat فرستنده", "الزامی", "عرض جغرافیایی محل بارگیری", "32.402286", "وب + WS"],
    ["long فرستنده", "الزامی", "طول جغرافیایی محل بارگیری", "51.381595", "وب + WS"],
    ["آدرس فرستنده", "توصیه‌شده", "آدرس متنی محل بارگیری؛ اگر خالی باشد از مختصات ساخته می‌شود", "اصفهان - خیابان آزادی", "وب"],
    ["نام گیرنده", "الزامی", "نام شخص یا شرکت", "رضا سیار", "وب + WS"],
    ["کد ملی گیرنده", "توصیه‌شده", "برای سازگاری کامل 10 رقمی پر شود", "1234567891", "WS و فرم گیرنده"],
    ["موبایل گیرنده", "الزامی", "شماره موبایل", "09185365222", "وب + WS"],
    ["تلفن گیرنده", "اختیاری", "بدون خط تیره", "03112345678", "وب + WS"],
    ["کد پستی گیرنده", "توصیه‌شده", "کد پستی 10 رقمی", "1234567891", "وب + WS"],
    ["lat گیرنده", "الزامی", "عرض جغرافیایی مقصد", "32.860259", "وب + WS"],
    ["long گیرنده", "الزامی", "طول جغرافیایی مقصد", "51.526419", "وب + WS"],
    ["آدرس گیرنده", "توصیه‌شده", "آدرس متنی مقصد؛ اگر خالی باشد از مختصات ساخته می‌شود", "مشهد - خیابان امام رضا", "وب"],
    ["کد نوع بار", "الزامی", "شناسه عددی نوع بار (برای WS)", "4618", "وب + WS"],
    ["نام نوع بار", "توصیه‌شده", "نام متنی نوع بار جهت انتخاب در dropdown فرم وب", "عمومی", "وب"],
    ["کد نوع بسته بندی (لیست)", "الزامی", "کد/عنوان بسته‌بندی", "18076#18076", "WS / سازگاری کامل"],
    ["نوع ناوگان", "توصیه‌شده", "نوع خودرو برای dropdown فرم وب (کامیون / وانت / ...)", "کامیون", "وب"],
    ["رمز عبور راننده (فقط برای حمل)", "اختیاری", "فقط در سناریوهای حمل", "@DriverPass1", "سناریوی حمل"],
    ["نام کاربری اکانت ثبت", "الزامی", "نام کاربری ورود UTCMS", "9907172420", "وب"],
    ["رمز عبور اکانت ثبت", "الزامی", "رمز عبور ورود UTCMS", "@Aaaa9000111", "وب"],
    ["فاصله بین شروع و پایان حمل (دقیقه)", "اختیاری", "عدد صحیح؛ 0 یعنی بدون محدودیت", "0", "وب (shipping_options)"],
    ["تاریخ پایان حمل", "اختیاری", "تاریخ شمسی پایان حمل مثل 1403-05-20؛ خالی بگذارید اگر ندارید", "", "وب (shipping_options)"],
    ["نام کاربری راننده (فقط برای حمل)", "اختیاری", "در صورت نیاز حمل", "9907172420", "سناریوی حمل"],
    ["ارسال پیامک به فرستنده (لیست)", "توصیه‌شده", "بله یا خیر", "خیر", "فرم تکمیلی"],
    ["بیمه اختیاری بار (لیست)", "توصیه‌شده", "بله یا خیر", "خیر", "فرم تکمیلی"],
    ["شناسه باربری", "توصیه‌شده", "برای WS/API کامل، کد باربری", "5845550", "WS"],
    ["ارتباط کاربر با خودرو", "اختیاری", "در فایل‌های عملیاتی موجود بوده است", "1", "سازگاری فایل"],
]


def _column_name(index: int) -> str:
    result = []
    current = index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def _xml_escape(value: str) -> str:
    return escape(value, {'"': "&quot;", "'": "&apos;"})


class SharedStrings:
    def __init__(self) -> None:
        self.items: List[str] = []
        self.index_by_value: dict[str, int] = {}

    def add(self, value: str) -> int:
        text = str(value)
        if text in self.index_by_value:
            return self.index_by_value[text]
        index = len(self.items)
        self.items.append(text)
        self.index_by_value[text] = index
        return index

    def to_xml(self) -> str:
        body = "".join(
            f"<si><t xml:space=\"preserve\">{_xml_escape(item)}</t></si>"
            for item in self.items
        )
        count = len(self.items)
        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<sst xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
            f"count=\"{count}\" uniqueCount=\"{count}\">{body}</sst>"
        )


def _sheet_xml(
    rows: Iterable[Iterable[str]],
    shared_strings: SharedStrings,
    freeze_header: bool = False,
    rtl: bool = True,
    auto_filter: str | None = None,
) -> str:
    row_xml_parts: List[str] = []
    max_col = 0

    for row_number, row in enumerate(rows, start=1):
        cells_xml: List[str] = []
        row_values = list(row)
        max_col = max(max_col, len(row_values))
        for col_number, value in enumerate(row_values, start=1):
            if value is None or value == "":
                continue
            cell_ref = f"{_column_name(col_number)}{row_number}"
            shared_index = shared_strings.add(str(value))
            cells_xml.append(f"<c r=\"{cell_ref}\" t=\"s\"><v>{shared_index}</v></c>")
        row_xml_parts.append(f"<row r=\"{row_number}\">{''.join(cells_xml)}</row>")

    dimension_ref = "A1"
    if max_col and row_xml_parts:
        dimension_ref = f"A1:{_column_name(max_col)}{len(row_xml_parts)}"

    sheet_view = "<sheetView workbookViewId=\"0\""
    if rtl:
        sheet_view += " rightToLeft=\"1\""
    sheet_view += ">"
    if freeze_header:
        sheet_view += (
            "<pane ySplit=\"1\" topLeftCell=\"A2\" activePane=\"bottomLeft\" state=\"frozen\"/>"
            "<selection pane=\"bottomLeft\" activeCell=\"A2\" sqref=\"A2\"/>"
        )
    sheet_view += "</sheetView>"

    auto_filter_xml = f"<autoFilter ref=\"{auto_filter}\"/>" if auto_filter else ""

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        f"<dimension ref=\"{dimension_ref}\"/>"
        f"<sheetViews>{sheet_view}</sheetViews>"
        "<sheetFormatPr defaultRowHeight=\"15\"/>"
        f"{auto_filter_xml}"
        f"<sheetData>{''.join(row_xml_parts)}</sheetData>"
        "<pageMargins left=\"0.7\" right=\"0.7\" top=\"0.75\" bottom=\"0.75\" "
        "header=\"0.3\" footer=\"0.3\"/>"
        "</worksheet>"
    )


def _content_types_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet1.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet2.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "<Override PartName=\"/xl/styles.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>"
        "<Override PartName=\"/xl/sharedStrings.xml\" "
        "ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml\"/>"
        "<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/>"
        "<Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>"
        "</Types>"
    )


def _root_rels_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>"
        "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/>"
        "<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/>"
        "</Relationships>"
    )


def _workbook_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        "<bookViews><workbookView xWindow=\"0\" yWindow=\"0\" windowWidth=\"24000\" windowHeight=\"14000\"/></bookViews>"
        "<sheets>"
        "<sheet name=\"ورود اطلاعات\" sheetId=\"1\" r:id=\"rId1\"/>"
        "<sheet name=\"راهنما\" sheetId=\"2\" r:id=\"rId2\"/>"
        "</sheets>"
        "</workbook>"
    )


def _workbook_rels_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>"
        "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet2.xml\"/>"
        "<Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>"
        "<Relationship Id=\"rId4\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings\" Target=\"sharedStrings.xml\"/>"
        "</Relationships>"
    )


def _styles_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">"
        "<fonts count=\"1\"><font><sz val=\"11\"/><name val=\"Calibri\"/></font></fonts>"
        "<fills count=\"2\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill></fills>"
        "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>"
        "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>"
        "<cellXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/></cellXfs>"
        "<cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles>"
        "</styleSheet>"
    )


def _core_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" "
        "xmlns:dc=\"http://purl.org/dc/elements/1.1/\" "
        "xmlns:dcterms=\"http://purl.org/dc/terms/\" "
        "xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" "
        "xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
        "<dc:title>Waybill Excel Template</dc:title>"
        "<dc:creator>Codex CLI</dc:creator>"
        "</cp:coreProperties>"
    )


def _app_xml() -> str:
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" "
        "xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\">"
        "<Application>Codex CLI</Application>"
        "</Properties>"
    )


def generate_template(output_path: Path) -> Path:
    shared_strings = SharedStrings()
    data_sheet = _sheet_xml(
        rows=[DATA_HEADERS, SAMPLE_ROW],
        shared_strings=shared_strings,
        freeze_header=True,
        rtl=True,
        auto_filter=f"A1:{_column_name(len(DATA_HEADERS))}2",
    )
    guide_sheet = _sheet_xml(
        rows=GUIDE_ROWS,
        shared_strings=shared_strings,
        freeze_header=False,
        rtl=True,
        auto_filter=None,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml())
        archive.writestr("_rels/.rels", _root_rels_xml())
        archive.writestr("docProps/core.xml", _core_xml())
        archive.writestr("docProps/app.xml", _app_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml())
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_rels_xml())
        archive.writestr("xl/styles.xml", _styles_xml())
        archive.writestr("xl/sharedStrings.xml", shared_strings.to_xml())
        archive.writestr("xl/worksheets/sheet1.xml", data_sheet)
        archive.writestr("xl/worksheets/sheet2.xml", guide_sheet)
    return output_path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    output_path = project_root / "exel-data" / "قالب_کامل_ورود_بارنامه.xlsx"
    generate_template(output_path)
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
