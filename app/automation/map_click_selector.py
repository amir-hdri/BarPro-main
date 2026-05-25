"""
سیستم انتخاب مکان بر اساس کلیک کاربر روی نقشه
کاربر با کلیک روی نقشه، مبدا و مقصد را انتخاب می‌کند
"""

import asyncio
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from playwright.async_api import Page

logger = logging.getLogger(__name__)


@dataclass
class ClickLocation:
    """مختصات یک نقطه انتخاب شده با کلیک"""
    latitude: float
    longitude: float
    pixel_x: int
    pixel_y: int
    address: Optional[str] = None
    label: Optional[str] = None  # 'origin' or 'destination'


@dataclass
class ClickSelection:
    """نتیجه انتخاب با کلیک"""
    origin: Optional[ClickLocation] = None
    destination: Optional[ClickLocation] = None
    map_bounds: Optional[Dict[str, float]] = None
    selection_complete: bool = False


class MapClickSelector:
    """
    مدیریت انتخاب مبدا و مقصد با کلیک کاربر روی نقشه
    
    نحوه کار:
    ۱. فعال کردن حالت انتخاب روی نقشه
    ۲. گوش دادن به رویداد کلیک
    ۳. دریافت مختصات نقطه انتخاب شده
    ۴. نمایش مارکر روی نقشه
    ۵. ذخیره نقطه به عنوان مبدا یا مقصد
    """

    def __init__(self, page: Page):
        self.page = page
        self.selection = ClickSelection()
        self._listening = False
        self._map_initialized = False

    async def initialize_map_click_mode(self) -> bool:
        """
        فعال کردن حالت انتخاب با کلیک روی نقشه
        
        Returns:
            True اگر موفق شد حالت کلیک را فعال کند
        """
        try:
            # تزریق JavaScript برای گوش دادن به کلیک‌ها
            await self.page.evaluate("""
                () => {
                    // ایجاد namespace برای ذخیره نقاط
                    if (!window.__utcms_map_clicks) {
                        window.__utcms_map_clicks = {
                            origin: null,
                            destination: null,
                            markers: [],
                            listeners: []
                        };
                    }

                    // تابع اضافه کردن مارکر
                    window.__utcms_add_marker = function(lat, lng, label) {
                        const mapClicks = window.__utcms_map_clicks;
                        
                        // تلاش برای اضافه کردن مارکر به نقشه‌های مختلف
                        // Google Maps
                        if (typeof google !== 'undefined' && google.maps) {
                            const mapElement = document.querySelector('.gm-style');
                            if (mapElement && google.maps.Map.getMap) {
                                const map = google.maps.Map.getMap(mapElement);
                                if (map) {
                                    const marker = new google.maps.Marker({
                                        position: { lat: lat, lng: lng },
                                        map: map,
                                        label: label,
                                        title: label === 'origin' ? 'مبدا' : 'مقصد'
                                    });
                                    mapClicks.markers.push(marker);
                                    return true;
                                }
                            }
                        }

                        // Leaflet
                        if (typeof L !== 'undefined') {
                            const mapElement = document.querySelector('.leaflet-container');
                            if (mapElement && mapElement._leaflet_map) {
                                const marker = L.marker([lat, lng]).addTo(mapElement._leaflet_map);
                                marker.bindTooltip(label === 'origin' ? 'مبدا' : 'مقصد');
                                mapClicks.markers.push(marker);
                                return true;
                            }
                        }

                        // OpenLayers
                        const olMap = document.querySelector('.ol-map');
                        if (olMap && olMap._map) {
                            // OpenLayers marker logic
                            return true;
                        }

                        // Mapbox
                        if (typeof mapboxgl !== 'undefined' && window.map) {
                            const el = document.createElement('div');
                            el.className = 'marker';
                            el.innerHTML = `<div style="
                                background: ${label === 'origin' ? '#10b981' : '#ef4444'};
                                color: white;
                                padding: 4px 8px;
                                border-radius: 4px;
                                font-size: 12px;
                                font-weight: bold;
                            ">${label === 'origin' ? 'مبدا' : 'مقصد'}</div>`;
                            
                            new mapboxgl.Marker(el)
                                .setLngLat([lng, lat])
                                .addTo(window.map);
                            return true;
                        }

                        return false;
                    };

                    // تابع پاک کردن مارکرها
                    window.__utcms_clear_markers = function() {
                        const mapClicks = window.__utcms_map_clicks;
                        
                        // Google Maps
                        if (typeof google !== 'undefined' && google.maps) {
                            mapClicks.markers.forEach(marker => marker.setMap(null));
                        }
                        
                        // Leaflet
                        mapClicks.markers.forEach(marker => {
                            if (marker.remove) marker.remove();
                        });

                        mapClicks.markers = [];
                        mapClicks.origin = null;
                        mapClicks.destination = null;
                    };

                    return true;
                }
            """)
            
            self._map_initialized = True
            logger.info("map_click_mode_initialized")
            return True
            
        except Exception as e:
            logger.error(f"failed_to_initialize_map_click_mode: {e}")
            return False

    async def get_map_bounds(self) -> Optional[Dict[str, float]]:
        """
        دریافت محدوده فعلی نقشه
        
        Returns:
            Dict با کلیدهای north, south, east, west
        """
        try:
            bounds = await self.page.evaluate("""
                () => {
                    // Google Maps
                    if (typeof google !== 'undefined' && google.maps) {
                        const mapElement = document.querySelector('.gm-style');
                        if (mapElement) {
                            const map = google.maps.Map.getMap(mapElement);
                            if (map) {
                                const bounds = map.getBounds();
                                if (bounds) {
                                    return {
                                        north: bounds.getNorthEast().lat(),
                                        south: bounds.getSouthWest().lat(),
                                        east: bounds.getNorthEast().lng(),
                                        west: bounds.getSouthWest().lng()
                                    };
                                }
                            }
                        }
                    }

                    // Leaflet
                    const leafletElement = document.querySelector('.leaflet-container');
                    if (leafletElement && leafletElement._leaflet_map) {
                        const bounds = leafletElement._leaflet_map.getBounds();
                        return {
                            north: bounds.getNorthEast().lat,
                            south: bounds.getSouthWest().lat,
                            east: bounds.getNorthEast().lng,
                            west: bounds.getSouthWest().lng
                        };
                    }

                    // Mapbox
                    if (typeof mapboxgl !== 'undefined' && window.map) {
                        const bounds = window.map.getBounds();
                        return {
                            north: bounds.getNorthEast().lat,
                            south: bounds.getSouthWest().lat,
                            east: bounds.getNorthEast().lng,
                            west: bounds.getSouthWest().lng
                        };
                    }

                    return null;
                }
            """)
            
            return bounds
            
        except Exception as e:
            logger.error(f"failed_to_get_map_bounds: {e}")
            return None

    async def wait_for_user_click(self, timeout_ms: int = 60000) -> Optional[ClickLocation]:
        """
        انتظار برای کلیک کاربر روی نقشه
        
        Args:
            timeout_ms: حداکثر زمان انتظار به میلی‌ثانیه
            
        Returns:
            ClickLocation شامل مختصات نقطه انتخاب شده
        """
        try:
            # اطمینان از فعال بودن حالت کلیک
            if not self._map_initialized:
                await self.initialize_map_click_mode()

            # تنظیم event listener برای کلیک
            await self.page.evaluate("""
                () => {
                    return new Promise((resolve) => {
                        const mapContainers = [
                            document.querySelector('.gm-style'),
                            document.querySelector('.leaflet-container'),
                            document.querySelector('.ol-map'),
                            document.querySelector('#map'),
                            document.querySelector('.map')
                        ].filter(el => el !== null);

                        if (mapContainers.length === 0) {
                            resolve(null);
                            return;
                        }

                        const handleClick = async (event) => {
                            // جلوگیری از propagation
                            event.stopPropagation();

                            let lat, lng;

                            // Google Maps
                            if (typeof google !== 'undefined' && google.maps && event.latLng) {
                                lat = event.latLng.lat();
                                lng = event.latLng.lng();
                            }
                            // Leaflet
                            else if (event.latlng) {
                                lat = event.latlng.lat;
                                lng = event.latlng.lng;
                            }
                            // محاسبه از pixel position
                            else {
                                const mapElement = mapContainers[0];
                                const rect = mapElement.getBoundingClientRect();
                                const x = event.clientX - rect.left;
                                const y = event.clientY - rect.top;
                                
                                // تلاش برای تبدیل pixel به lat/lng
                                const coords = await window.__utcms_pixel_to_coords(x, y, rect.width, rect.height);
                                if (coords) {
                                    lat = coords.lat;
                                    lng = coords.lng;
                                }
                            }

                            if (lat && lng) {
                                resolve({
                                    latitude: lat,
                                    longitude: lng,
                                    pixel_x: event.clientX,
                                    pixel_y: event.clientY
                                });
                            }
                        };

                        // اضافه کردن listener به تمام کانتینرهای نقشه
                        mapContainers.forEach(container => {
                            container.addEventListener('click', handleClick, { once: true });
                        });

                        // Timeout
                        setTimeout(() => resolve(null), """ + str(timeout_ms) + """);
                    });
                }
            """)

            # انتظار برای نتیجه
            result = await self.page.evaluate("""
                () => window.__utcms_pending_click_promise || null
            """)

            if result:
                return ClickLocation(
                    latitude=result['latitude'],
                    longitude=result['longitude'],
                    pixel_x=result['pixel_x'],
                    pixel_y=result['pixel_y']
                )

            return None

        except Exception as e:
            logger.error(f"failed_to_wait_for_user_click: {e}")
            return None

    async def add_marker_to_map(self, lat: float, lng: float, label: str = 'point') -> bool:
        """
        اضافه کردن مارکر به نقشه در نقطه انتخاب شده
        
        Args:
            lat: عرض جغرافیایی
            lng: طول جغرافیایی
            label: برچسب مارکر (origin/destination)
            
        Returns:
            True اگر موفق شد مارکر اضافه کند
        """
        try:
            success = await self.page.evaluate("""
                (params) => {
                    if (window.__utcms_add_marker) {
                        return window.__utcms_add_marker(params.lat, params.lng, params.label);
                    }
                    return false;
                }
            """, {"lat": lat, "lng": lng, "label": label})

            if success:
                logger.info(f"marker_added: {label} at ({lat}, {lng})")
            else:
                logger.warning(f"failed_to_add_marker: {label} at ({lat}, {lng})")

            return success

        except Exception as e:
            logger.error(f"error_adding_marker: {e}")
            return False

    async def clear_markers(self) -> bool:
        """پاک کردن تمام مارکرهای روی نقشه"""
        try:
            await self.page.evaluate("""
                () => {
                    if (window.__utcms_clear_markers) {
                        window.__utcms_clear_markers();
                    }
                }
            """)
            
            self.selection = ClickSelection()
            logger.info("markers_cleared")
            return True

        except Exception as e:
            logger.error(f"error_clearing_markers: {e}")
            return False

    async def select_origin_by_click(self, timeout_ms: int = 60000) -> Optional[ClickLocation]:
        """
        انتخاب مبدا با کلیک کاربر
        
        Args:
            timeout_ms: حداکثر زمان انتظار
            
        Returns:
            ClickLocation نقطه انتخاب شده
        """
        logger.info("waiting_for_user_to_select_origin")
        
        # نمایش پیام به کاربر
        await self.page.evaluate("""
            () => {
                const notification = document.createElement('div');
                notification.id = 'utcms-notification';
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: #3b82f6;
                    color: white;
                    padding: 15px 30px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: bold;
                    z-index: 10000;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    direction: rtl;
                `;
                notification.textContent = 'لطفاً مبدا را روی نقشه کلیک کنید';
                document.body.appendChild(notification);

                setTimeout(() => {
                    const el = document.getElementById('utcms-notification');
                    if (el) el.remove();
                }, 5000);
            }
        """)

        location = await self.wait_for_user_click(timeout_ms)
        
        if location:
            location.label = 'origin'
            self.selection.origin = location
            await self.add_marker_to_map(location.latitude, location.longitude, 'origin')
            logger.info(f"origin_selected: ({location.latitude}, {location.longitude})")
            
            # نمایش پیام موفقیت
            await self.page.evaluate("""
                () => {
                    const notification = document.createElement('div');
                    notification.style.cssText = `
                        position: fixed;
                        top: 20px;
                        left: 50%;
                        transform: translateX(-50%);
                        background: #10b981;
                        color: white;
                        padding: 15px 30px;
                        border-radius: 8px;
                        font-size: 16px;
                        font-weight: bold;
                        z-index: 10000;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                        direction: rtl;
                    `;
                    notification.textContent = '✓ مبدا انتخاب شد - حالا مقصد را کلیک کنید';
                    document.body.appendChild(notification);

                    setTimeout(() => notification.remove(), 3000);
                }
            """)
        
        return location

    async def select_destination_by_click(self, timeout_ms: int = 60000) -> Optional[ClickLocation]:
        """
        انتخاب مقصد با کلیک کاربر
        
        Args:
            timeout_ms: حداکثر زمان انتظار
            
        Returns:
            ClickLocation نقطه انتخاب شده
        """
        logger.info("waiting_for_user_to_select_destination")
        
        # نمایش پیام به کاربر
        await self.page.evaluate("""
            () => {
                const notification = document.createElement('div');
                notification.id = 'utcms-notification';
                notification.style.cssText = `
                    position: fixed;
                    top: 20px;
                    left: 50%;
                    transform: translateX(-50%);
                    background: #ef4444;
                    color: white;
                    padding: 15px 30px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: bold;
                    z-index: 10000;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                    direction: rtl;
                `;
                notification.textContent = 'لطفاً مقصد را روی نقشه کلیک کنید';
                document.body.appendChild(notification);

                setTimeout(() => {
                    const el = document.getElementById('utcms-notification');
                    if (el) el.remove();
                }, 5000);
            }
        """)

        location = await self.wait_for_user_click(timeout_ms)
        
        if location:
            location.label = 'destination'
            self.selection.destination = location
            await self.add_marker_to_map(location.latitude, location.longitude, 'destination')
            logger.info(f"destination_selected: ({location.latitude}, {location.longitude})")
            
            # نمایش پیام موفقیت
            await self.page.evaluate("""
                () => {
                    const notification = document.createElement('div');
                    notification.style.cssText = `
                        position: fixed;
                        top: 20px;
                        left: 50%;
                        transform: translateX(-50%);
                        background: #10b981;
                        color: white;
                        padding: 15px 30px;
                        border-radius: 8px;
                        font-size: 16px;
                        font-weight: bold;
                        z-index: 10000;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
                        direction: rtl;
                    `;
                    notification.textContent = '✓ مقصد انتخاب شد - در حال ثبت بارنامه...';
                    document.body.appendChild(notification);

                    setTimeout(() => notification.remove(), 3000);
                }
            """)
        
        return location

    async def select_both_locations_by_click(
        self,
        origin_timeout: int = 60000,
        destination_timeout: int = 60000
    ) -> ClickSelection:
        """
        انتخاب هم مبدا و هم مقصد با کلیک کاربر
        
        Args:
            origin_timeout: زمان انتظار برای انتخاب مبدا
            destination_timeout: زمان انتظار برای انتخاب مقصد
            
        Returns:
            ClickSelection شامل هر دو نقطه
        """
        # پاک کردن انتخاب‌های قبلی
        await self.clear_markers()
        
        # انتخاب مبدا
        origin = await self.select_origin_by_click(origin_timeout)
        if not origin:
            logger.warning("origin_selection_failed_or_timeout")
            return self.selection
        
        # مکث کوتاه
        await asyncio.sleep(1)
        
        # انتخاب مقصد
        destination = await self.select_destination_by_click(destination_timeout)
        if not destination:
            logger.warning("destination_selection_failed_or_timeout")
            return self.selection
        
        self.selection.selection_complete = True
        self.selection.map_bounds = await self.get_map_bounds()
        
        logger.info(
            f"both_locations_selected: "
            f"origin=({origin.latitude}, {origin.longitude}), "
            f"destination=({destination.latitude}, {destination.longitude})"
        )
        
        return self.selection

    def get_selection_result(self) -> Dict[str, Any]:
        """
        دریافت نتیجه انتخاب به صورت دیکشنری
        
        Returns:
            دیکشنری شامل اطلاعات مبدا و مقصد
        """
        result = {
            "origin": None,
            "destination": None,
            "complete": self.selection.selection_complete
        }
        
        if self.selection.origin:
            result["origin"] = {
                "lat": self.selection.origin.latitude,
                "lng": self.selection.origin.longitude,
                "address": self.selection.origin.address
            }
        
        if self.selection.destination:
            result["destination"] = {
                "lat": self.selection.destination.latitude,
                "lng": self.selection.destination.longitude,
                "address": self.selection.destination.address
            }
        
        return result


# Singleton instance
_map_click_selector: Optional[MapClickSelector] = None


def get_map_click_selector(page: Page) -> MapClickSelector:
    """دریافت instance از MapClickSelector"""
    global _map_click_selector
    if _map_click_selector is None:
        _map_click_selector = MapClickSelector(page)
    return _map_click_selector
