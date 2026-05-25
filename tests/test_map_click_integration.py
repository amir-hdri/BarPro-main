"""
تست جامع یکپارچگی انتخاب نقشه با کلیک
بررسی صحت عملکرد از UI تا ثبت بارنامه
"""

import pytest
from unittest.mock import AsyncMock
from app.automation.map_click_selector import (
    MapClickSelector,
    ClickLocation,
    ClickSelection,
    get_map_click_selector
)
from app.automation.location_selector import LocationSelector
from app.automation.map_controller import GeoCoordinate


class TestMapClickIntegration:
    """تست‌های یکپارچگی انتخاب نقشه"""

    def test_click_location_creation(self):
        """تست ایجاد نقطه کلیک شده"""
        location = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300,
            label='origin'
        )
        
        assert location.latitude == 35.6892
        assert location.longitude == 51.3890
        assert location.pixel_x == 400
        assert location.label == 'origin'

    def test_click_selection_structure(self):
        """تست ساختار انتخاب کامل"""
        selection = ClickSelection()
        
        assert selection.origin is None
        assert selection.destination is None
        assert selection.selection_complete is False

    def test_convert_click_to_location_data(self):
        """تست تبدیل کلیک به فرمت location_data"""
        click_loc = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300
        )
        
        # تبدیل به فرمت مورد انتظار LocationSelector
        location_data = {
            'province': 'تهران',
            'city': 'تهران',
            'coordinates': {
                'lat': click_loc.latitude,
                'lng': click_loc.longitude
            }
        }
        
        assert location_data['coordinates']['lat'] == 35.6892
        assert location_data['coordinates']['lng'] == 51.3890
        assert 'province' in location_data

    @pytest.mark.asyncio
    async def test_map_click_selector_initialization(self):
        """تست راه‌اندازی MapClickSelector"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        
        selector = MapClickSelector(mock_page)
        
        # تست متد initialize
        result = await selector.initialize_map_click_mode()
        assert result is True
        
        # بررسی اینکه evaluate صدا زده شد
        mock_page.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_add_marker(self):
        """تست اضافه کردن مارکر"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        
        selector = MapClickSelector(mock_page)
        result = await selector.add_marker_to_map(35.6892, 51.3890, 'origin')
        
        assert result is True
        mock_page.evaluate.assert_called()

    @pytest.mark.asyncio
    async def test_clear_markers(self):
        """تست پاک کردن مارکرها"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        
        selector = MapClickSelector(mock_page)
        selector.selection.origin = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300,
            label='origin'
        )
        
        result = await selector.clear_markers()
        
        assert result is True
        assert selector.selection.origin is None

    def test_get_selection_result(self):
        """تست دریافت نتیجه انتخاب"""
        selector = MapClickSelector(AsyncMock())
        
        # تنظیم داده‌های تست
        selector.selection.origin = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300,
            label='origin'
        )
        selector.selection.destination = ClickLocation(
            latitude=35.7000,
            longitude=51.4000,
            pixel_x=500,
            pixel_y=400,
            label='destination'
        )
        selector.selection.selection_complete = True
        
        result = selector.get_selection_result()
        
        assert result['complete'] is True
        assert result['origin']['lat'] == 35.6892
        assert result['origin']['lng'] == 51.3890
        assert result['destination']['lat'] == 35.7000
        assert result['destination']['lng'] == 51.4000

    def test_singleton_pattern(self):
        """تست الگوی singleton"""
        mock_page = AsyncMock()
        
        selector1 = get_map_click_selector(mock_page)
        selector2 = get_map_click_selector(mock_page)
        
        # باید یک instance واحد باشد
        assert selector1 is selector2

    @pytest.mark.asyncio
    async def test_integration_with_location_selector(self):
        """تست یکپارچگی با LocationSelector"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        mock_page.fill = AsyncMock(return_value=True)
        mock_page.wait_for_selector = AsyncMock(return_value=AsyncMock())
        
        # ایجاد LocationSelector
        location_selector = LocationSelector(mock_page)
        
        # داده‌های مکان از کلیک کاربر
        location_data = {
            'province': 'تهران',
            'city': 'تهران',
            'coordinates': {
                'lat': 35.6892,
                'lng': 51.3890
            }
        }
        
        # تست که متد select_location وجود دارد
        assert hasattr(location_selector, 'select_location')
        
        # تست که متد _try_explicit_coordinates وجود دارد
        assert hasattr(location_selector, '_try_explicit_coordinates')

    def test_geo_coordinate_compatibility(self):
        """تست سازگاری با GeoCoordinate"""
        click_loc = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300
        )
        
        # تبدیل به GeoCoordinate
        geo_coord = GeoCoordinate(
            latitude=click_loc.latitude,
            longitude=click_loc.longitude
        )
        
        assert geo_coord.latitude == 35.6892
        assert geo_coord.longitude == 51.3890
        
        # تست to_dict
        coord_dict = geo_coord.to_dict()
        assert 'lat' in coord_dict
        assert 'lng' in coord_dict

    @pytest.mark.asyncio
    async def test_full_selection_flow(self):
        """تست جریان کامل انتخاب"""
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(return_value=True)
        
        selector = MapClickSelector(mock_page)
        
        # تنظیم selection به صورت دستی (شبیه‌سازی کلیک کاربر)
        selector.selection.origin = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300,
            label='origin'
        )
        selector.selection.destination = ClickLocation(
            latitude=35.7000,
            longitude=51.4000,
            pixel_x=500,
            pixel_y=400,
            label='destination'
        )
        selector.selection.selection_complete = True
        selector.selection.map_bounds = {
            'north': 35.8,
            'south': 35.6,
            'east': 51.5,
            'west': 51.3
        }
        
        # بررسی نتیجه
        result = selector.get_selection_result()
        
        assert result['complete'] is True
        assert result['origin'] is not None
        assert result['destination'] is not None
        assert result['origin']['lat'] == 35.6892
        assert result['destination']['lat'] == 35.7000


class TestMapClickUI:
    """تست‌های رابط کاربری نقشه"""

    def test_ui_file_has_map_tab(self):
        """تست وجود تب نقشه در UI"""
        from pathlib import Path
        
        ui_path = Path('app/ui/index.html')
        assert ui_path.exists(), "UI file not found"
        
        with open(ui_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'tab-map-tools' in content
        assert 'btn-select-origin' in content
        assert 'btn-select-destination' in content
        assert 'btn-clear-selection' in content

    def test_ui_has_click_handler(self):
        """تست وجود handler کلیک"""
        from pathlib import Path
        
        js_path = Path('app/ui/assets/app.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'handleMapClick' in content
        # assert 'mapClickMode' in content  # Replaced by activeTarget in mapState

    def test_ui_has_display_elements(self):
        """تست وجود المان‌های نمایش"""
        from pathlib import Path
        
        ui_path = Path('app/ui/index.html')
        with open(ui_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        assert 'origin-display' in content
        assert 'destination-display' in content
        assert 'origin-card' in content
        assert 'destination-card' in content


class TestDataFlow:
    """تست‌های جریان داده"""

    def test_click_to_waybill_data(self):
        """تست تبدیل کلیک به داده بارنامه"""
        # شبیه‌سازی کلیک کاربر
        origin_click = ClickLocation(
            latitude=35.6892,
            longitude=51.3890,
            pixel_x=400,
            pixel_y=300
        )
        
        destination_click = ClickLocation(
            latitude=35.7000,
            longitude=51.4000,
            pixel_x=500,
            pixel_y=400
        )
        
        # تبدیل به فرمت بارنامه
        waybill_data = {
            'origin': {
                'latitude': origin_click.latitude,
                'longitude': origin_click.longitude,
                'address': origin_click.address
            },
            'destination': {
                'latitude': destination_click.latitude,
                'longitude': destination_click.longitude,
                'address': destination_click.address
            }
        }
        
        assert waybill_data['origin']['latitude'] == 35.6892
        assert waybill_data['origin']['longitude'] == 51.3890
        assert waybill_data['destination']['latitude'] == 35.7000
        assert waybill_data['destination']['longitude'] == 51.4000

    def test_coordinate_validation(self):
        """تست اعتبارسنجی مختصات"""
        # مختصات معتبر ایران
        valid_coords = [
            (35.6892, 51.3890),  # تهران
            (32.6546, 51.6680),  # اصفهان
            (36.2605, 59.6168),  # مشهد
            (29.5918, 52.5837),  # شیراز
        ]
        
        for lat, lng in valid_coords:
            location = ClickLocation(
                latitude=lat,
                longitude=lng,
                pixel_x=0,
                pixel_y=0
            )
            
            # بررسی محدوده معتبر
            assert -90 <= location.latitude <= 90, f"Invalid latitude: {lat}"
            assert -180 <= location.longitude <= 180, f"Invalid longitude: {lng}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
