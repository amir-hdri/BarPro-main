"""Route distance/time service: Neshan API with haversine fallback + Redis cache.

Resolution order: Redis cache → Neshan API → local haversine fallback.
The Neshan endpoint is a fixed host, so there is no user-controlled URL (no SSRF).
"""

from __future__ import annotations

import json
import logging

import httpx

from app.core.config import utcms_config
from app.core.distance import estimate_time, road_estimate
from app.core.redis import redis_manager

logger = logging.getLogger(__name__)


def _cache_key(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> str:
    return f"route:{origin_lat:.4f},{origin_lng:.4f}:{dest_lat:.4f},{dest_lng:.4f}"


def _haversine_fallback(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    """Local road estimate when Neshan is unavailable or unconfigured."""
    road_km = road_estimate(origin_lat, origin_lng, dest_lat, dest_lng)
    return {
        "distance_km": round(road_km, 2),
        "duration_min": round(estimate_time(road_km)),
        "source": "haversine_fallback",
    }


async def _fetch_neshan(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict | None:
    api_key = (utcms_config.NESHAN_API_KEY or "").strip()
    if not api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=utcms_config.NESHAN_TIMEOUT_SECONDS) as client:
            resp = await client.get(
                "https://api.neshan.org/v4/direction",
                params={
                    "type": "car",
                    "origin": f"{origin_lat},{origin_lng}",
                    "destination": f"{dest_lat},{dest_lng}",
                },
                headers={"Api-Key": api_key},
            )
            resp.raise_for_status()
            data = resp.json()
            leg = data["routes"][0]["legs"][0]
            return {
                "distance_km": round(leg["distance"]["value"] / 1000.0, 2),
                "duration_min": round(leg["duration"]["value"] / 60.0),
                "source": "neshan",
            }
    except Exception as exc:  # noqa: BLE001 — fall back on any provider failure
        logger.warning("Neshan direction failed, falling back to haversine: %s", exc)
        return None


async def get_route_distance(origin_lat: float, origin_lng: float, dest_lat: float, dest_lng: float) -> dict:
    """Return ``{"distance_km", "duration_min", "source"}`` for a route."""
    key = _cache_key(origin_lat, origin_lng, dest_lat, dest_lng)
    redis = await redis_manager.get()
    if redis is not None:
        try:
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)
        except Exception as exc:  # noqa: BLE001 — cache is best-effort
            logger.debug("Route cache read failed: %s", exc)

    result = await _fetch_neshan(origin_lat, origin_lng, dest_lat, dest_lng)
    if result is None:
        # Fallback is never cached: it must not poison the key for the full TTL.
        return _haversine_fallback(origin_lat, origin_lng, dest_lat, dest_lng)

    if redis is not None:
        try:
            await redis.setex(key, utcms_config.NESHAN_CACHE_TTL_SECONDS, json.dumps(result))
        except Exception as exc:  # noqa: BLE001
            logger.debug("Route cache write failed: %s", exc)
    return result
