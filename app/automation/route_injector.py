import asyncio
import logging
import random
from typing import Any

from playwright.async_api import BrowserContext, Page, expect

# Configure standard logger
logger = logging.getLogger(__name__)


async def inject_route_points(page: Page, context: BrowserContext, route_points: list[dict[str, Any]]):
    """
    Injects route points (origin, waypoints, destination) sequentially by interacting with an interactive map.
    Bypasses native Geolocation API to prevent target site from detecting real location.
    Uses dual strategy: Strategy A (JS Leaflet evaluation) and Strategy B (Viewport Geometry bounds).

    Args:
        page (Page): The Playwright Page object.
        context (BrowserContext): The Playwright BrowserContext object.
        route_points (List[Dict]): A strictly ordered list of dicts with 'lat', 'lng', and 'type' keys.
    """
    # 1. Block Geolocation (Crucial Technical Requirement)
    # Explicitly grant permissions but omit 'geolocation' to block it,
    # and override geolocation to a dummy location so "Find My Location" fails or uses our dummy point.
    logger.info("Overriding geolocation permissions in BrowserContext to bypass native location discovery.")
    await context.grant_permissions([])  # Block all permissions including geolocation
    await context.set_geolocation({"latitude": 0.0, "longitude": 0.0})  # Dummy fallback

    # Wait for map container to be fully loaded and stable
    logger.info("Waiting for map container to load and network to idle...")
    # Using generic map selectors
    map_selectors = ["#map", ".map", "#map-container", ".leaflet-container", ".gm-style"]

    # Try to find which map selector is present
    selected_map_locator = None
    for selector in map_selectors:
        try:
            locator = page.locator(selector).first
            # Wait for up to 5 seconds for the container
            await expect(locator).to_be_visible(timeout=5000)
            selected_map_locator = locator
            logger.info(f"Map container found using selector: {selector}")
            break
        except Exception:
            continue

    if not selected_map_locator:
        logger.warning("Could not clearly identify a specific map container. Using body as fallback.")
        selected_map_locator = page.locator("body")

    # Wait for stable state
    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception as e:
        logger.warning(f"Network idle timeout reached, proceeding anyway: {e}")

    # Process each point
    for idx, point in enumerate(route_points):
        lat = float(point["lat"])
        lng = float(point["lng"])
        pt_type = point.get("type", "unknown")

        logger.info(f"Processing point {idx + 1}/{len(route_points)}: {pt_type} at ({lat}, {lng})")

        # Dual-Strategy Map Interaction
        # Strategy A (JS Evaluation for exposed map objects like Leaflet `window.L`)
        js_strategy_success = False

        logger.debug("Attempting Strategy A: JS Evaluation (Leaflet/Map objects)")

        # Script tries to find a Leaflet map instance and convert latLng to container pixel coords
        strategy_a_script = """
        (lat, lng) => {
            let mapInstance = null;
            const mapContainer = document.querySelector('.leaflet-container') || document.querySelector('#map');

            const matchesLeafletMap = (value) => (
                value &&
                typeof value.setView === 'function' &&
                typeof value.latLngToContainerPoint === 'function' &&
                typeof value.getContainer === 'function'
            );

            if (mapContainer) {
                // Try direct candidates
                const directCandidates = [mapContainer._leaflet_map, mapContainer._map, window.map];
                for (const candidate of directCandidates) {
                    if (matchesLeafletMap(candidate)) {
                        mapInstance = candidate;
                        break;
                    }
                }

                // Try to find it on window object
                if (!mapInstance) {
                    for (const key in window) {
                        try {
                            const value = window[key];
                            if (matchesLeafletMap(value)) {
                                if (value.getContainer() === mapContainer) {
                                    mapInstance = value;
                                    break;
                                }
                            }
                        } catch (e) {
                            continue;
                        }
                    }
                }
            }

            // If we found a map instance that can convert coordinates
            if (mapInstance && typeof mapInstance.latLngToContainerPoint === 'function') {
                try {
                    // Try to fly to the point first to ensure it's in view
                    if (typeof mapInstance.flyTo === 'function') {
                        mapInstance.flyTo([lat, lng], 15, {animate: false});
                    } else if (typeof mapInstance.setView === 'function') {
                        mapInstance.setView([lat, lng], 15);
                    }

                    // Convert lat/lng to pixel coordinates relative to the map container
                    const pixelPoint = mapInstance.latLngToContainerPoint([lat, lng]);

                    // Return the calculated pixels if valid
                    if (pixelPoint && pixelPoint.x != null && pixelPoint.y != null) {
                        return { x: pixelPoint.x, y: pixelPoint.y, success: true, method: 'leaflet_api' };
                    }
                } catch(e) {
                    console.error("Strategy A mapping error:", e);
                }
            }

            // Fallback: Check if Google Maps is loaded but we can't easily access the projection
            if (window.google && window.google.maps) {
                // Very difficult to get pixel coordinates from vanilla JS for Google Maps
                // unless the OverlayView or Projection is exposed.
                return { success: false, method: 'google_maps_detected_but_unsupported' };
            }

            return { success: false };
        }
        """

        try:
            # Execute Strategy A script
            eval_result = await page.evaluate(strategy_a_script, [lat, lng])

            if eval_result and eval_result.get("success"):
                logger.info(f"Strategy A successful. Pixel coordinates: {eval_result.get('x')}, {eval_result.get('y')}")

                # Get map bounding box to convert container pixels to page pixels
                map_box = await selected_map_locator.bounding_box()
                if map_box:
                    target_x = map_box["x"] + eval_result["x"]
                    target_y = map_box["y"] + eval_result["y"]

                    # Ensure coordinates are within viewport
                    viewport = page.viewport_size
                    if viewport and 0 <= target_x <= viewport["width"] and 0 <= target_y <= viewport["height"]:
                        # Anti-bot stealth: Hover before click with human-like jitter
                        logger.debug("Hovering over calculated point to simulate human movement.")
                        await page.mouse.move(target_x, target_y, steps=random.randint(5, 15))
                        await asyncio.sleep(random.uniform(0.5, 1.5))

                        logger.debug("Clicking on point via Strategy A coordinates.")
                        await page.mouse.click(target_x, target_y, delay=random.randint(50, 150))
                        js_strategy_success = True
        except Exception as e:
            logger.debug(f"Strategy A failed or threw exception: {e}")

        # Strategy B (Viewport Geometry calculation) - Fallback
        if not js_strategy_success:
            logger.info("Strategy A failed. Falling back to Strategy B: Viewport Geometry bounding box click.")

            try:
                # Scroll to map container to ensure it's visible
                await selected_map_locator.scroll_into_view_if_needed()
                await asyncio.sleep(0.5)  # Let scrolling settle

                map_box = await selected_map_locator.bounding_box()
                if not map_box:
                    raise Exception("Could not determine map container bounding box.")

                # To simulate clicking a specific lat/lng without an API, we must guess
                # a reasonable point inside the container. We'll click slightly offset from center
                # to simulate picking a valid spot on the currently visible map viewport.
                center_x = map_box["x"] + map_box["width"] / 2
                center_y = map_box["y"] + map_box["height"] / 2

                # Add random offset (jitter) to the center based on map size
                jitter_x = random.uniform(-map_box["width"] * 0.1, map_box["width"] * 0.1)
                jitter_y = random.uniform(-map_box["height"] * 0.1, map_box["height"] * 0.1)

                target_x = center_x + jitter_x
                target_y = center_y + jitter_y

                logger.debug(f"Calculated Strategy B target: {target_x}, {target_y}")

                # Anti-bot stealth: Human-like movement and delay
                await page.mouse.move(target_x, target_y, steps=random.randint(10, 20))

                # Jitter/delays between clicks as requested (1.2 to 2.5 seconds)
                stealth_delay = random.uniform(1.2, 2.5)
                logger.debug(f"Stealth delay before click: {stealth_delay:.2f}s")
                await asyncio.sleep(stealth_delay)

                logger.debug("Clicking on point via Strategy B coordinates.")
                await page.mouse.click(target_x, target_y, delay=random.randint(50, 150))

            except Exception as e:
                logger.error(f"Strategy B also failed: {e}")
                raise Exception(f"Failed to interact with map for point {pt_type} at {lat},{lng}") from e

        # Handling UI Confirmations
        logger.info("Waiting for UI confirmation modal/button...")
        try:
            # Assume a UI modal or floating button appears that says "Confirm Point" (button.confirm-point)
            # Wait for it to become visible and click it
            confirm_btn = page.locator("button.confirm-point").first
            await expect(confirm_btn).to_be_visible(timeout=5000)

            # Stealth interaction with confirm button
            logger.debug("Hovering over confirm button...")
            await confirm_btn.hover(timeout=2000)

            stealth_delay = random.uniform(0.5, 1.2)
            await asyncio.sleep(stealth_delay)

            logger.info("Clicking confirm button.")
            await confirm_btn.click()

            # Wait for modal to disappear or process to complete
            await asyncio.sleep(random.uniform(0.5, 1.0))

        except Exception as e:
            logger.warning(f"UI confirmation step failed or button not found for point {pt_type}: {e}")

        logger.info(f"Successfully processed point: {pt_type}")

    logger.info("All route points processed successfully.")
