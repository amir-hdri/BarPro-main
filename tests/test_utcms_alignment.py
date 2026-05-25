import unittest
from unittest.mock import AsyncMock

from app.automation.location_selector import LocationSelector
from app.automation.selectors import AuthSelectors, LocationSelectors


class TestUTCMSAlignment(unittest.TestCase):
    def test_location_prefix_aliases_cover_utcms_source_dest(self):
        selector = LocationSelector(AsyncMock())

        province_origin = selector._build_formatted_selectors(
            LocationSelectors.PROVINCE_TEMPLATES,
            prefix="Origin",
        )
        city_destination = selector._build_formatted_selectors(
            LocationSelectors.CITY_TEMPLATES,
            prefix="Destination",
        )
        address_origin = selector._build_formatted_selectors(
            LocationSelectors.ADDRESS_TEMPLATES,
            prefix="Origin",
        )

        self.assertIn('select[name="ddStateSource"]', province_origin)
        self.assertIn('select[name="ddCityDest"]', city_destination)
        self.assertIn('textarea[name="txtAddressSource"]', address_origin)

    def test_map_search_templates_cover_utcms_map_city_fields(self):
        selector = LocationSelector(AsyncMock())

        map_search_origin = selector._build_formatted_selectors(
            LocationSelectors.MAP_SEARCH_TEMPLATES,
            prefix="Origin",
            extra_aliases=["2"],
        )
        map_search_destination = selector._build_formatted_selectors(
            LocationSelectors.MAP_SEARCH_TEMPLATES,
            prefix="Destination",
            extra_aliases=["2"],
        )

        self.assertIn("#MapCity", map_search_origin)
        self.assertIn("#AddressSearch", map_search_origin)
        self.assertIn("#MapCity2", map_search_destination)
        self.assertIn("#AddressSearch2", map_search_destination)

    def test_auth_submit_and_waybill_markers_match_live_fields(self):
        self.assertIn("button[id='inter']", AuthSelectors.SUBMIT_SELECTORS)
        self.assertIn("select[name='ddStateSource']", AuthSelectors.WAYBILL_FORM_MARKERS)
        self.assertIn("button#btnGoLVL2", AuthSelectors.WAYBILL_FORM_MARKERS)


if __name__ == "__main__":
    unittest.main()
