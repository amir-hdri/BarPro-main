import pytest

from app.schemas.itmb_ws import WS01InsertBOLRequest
from scripts.generate_waybill_excel_template import DATA_HEADERS, SAMPLE_ROW, generate_template
from scripts.register_waybills_from_excel import build_ws_payload, read_xlsx, to_header_map
from scripts.register_waybills_web_from_excel import ReverseGeoResolver, _build_request


def test_generated_template_has_expected_headers(tmp_path):
    output_path = tmp_path / "template.xlsx"

    generate_template(output_path)

    rows = read_xlsx(output_path)
    header_map = to_header_map(rows[0])

    assert rows[0] == DATA_HEADERS
    assert all(index >= 0 for index in header_map.values())
    assert rows[1] == SAMPLE_ROW


@pytest.mark.asyncio
async def test_generated_template_sample_row_validates(tmp_path):
    output_path = tmp_path / "template.xlsx"

    generate_template(output_path)

    rows = read_xlsx(output_path)
    header_map = to_header_map(rows[0])

    ws_payload = build_ws_payload(rows[1], header_map, serial_seed=123456)
    WS01InsertBOLRequest.model_validate(ws_payload)

    geo = ReverseGeoResolver(enabled=False)
    try:
        _, excerpt, _ = await _build_request(
            row=rows[1],
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

    assert excerpt["plate"] == "39ع81984"
