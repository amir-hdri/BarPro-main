"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  TruckIcon,
  PlayIcon,
  StopIcon,
  ArrowPathIcon,
  CheckCircleIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import type * as LType from "leaflet";
import { api } from "@/lib/api";

/* ─────────────────── Types ─────────────────── */

interface ShippingWaypoint {
  lat: number;
  lon: number;
  speed: number;
  cum_km: number;
  type: number; // 1=origin, 2=intermediate, 3=destination
  ts: string;
  address?: string;
}

interface ShippingStatus {
  status: string;
  origin?: { lat: number; lng: number; address: string; city?: string };
  destination?: { lat: number; lng: number; address: string; city?: string };
  distance_km: number;
  direct_distance_km?: number;
  duration_hours?: number;
  duration_minutes?: number;
  estimated_duration_text?: string;
  remaining_duration_text?: string;
  traveled_km: number;
  remaining_km?: number;
  progress_pct: number;
  current_step: number;
  total_steps: number;
  waypoints: ShippingWaypoint[];
  gps_list: unknown[];
  doc_no?: string;
  measured_distance_km?: number;
}

export interface ShippingRouteMapProps {
  jobId: string;
  /** شماره سند بارنامه — for starting shipping */
  docNo?: string;
  /** آدرس مبدأ — exact user-entered text */
  originAddress?: string;
  /** آدرس مقصد — exact user-entered text */
  destAddress?: string;
  /** Origin coordinates (auto-extracted from payload) */
  originLat?: number;
  originLng?: number;
  /** Destination coordinates (auto-extracted from payload) */
  destLat?: number;
  destLng?: number;
}

/* ─────────────────── Component ─────────────────── */

export const ShippingRouteMap = memo(function ShippingRouteMap({
  jobId,
  docNo,
  originAddress = "",
  destAddress = "",
  originLat,
  originLng,
  destLat,
  destLng,
}: ShippingRouteMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<LType.Map | null>(null);
  const markersRef = useRef<LType.Marker[]>([]);
  const polylineRef = useRef<LType.Polyline | null>(null);
  const truckMarkerRef = useRef<LType.Marker | null>(null);

  const [status, setStatus] = useState<ShippingStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [measuredDistanceKm, setMeasuredDistanceKm] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const tileLayerRef = useRef<LType.TileLayer | null>(null);
  const tileErrors = useRef(0);
  const resizeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const scheduleInvalidate = useCallback((delayMs = 120) => {
    if (resizeTimer.current) clearTimeout(resizeTimer.current);
    resizeTimer.current = setTimeout(() => {
      leafletMap.current?.invalidateSize();
    }, delayMs);
  }, []);

  /* ── Fetch current status (abort-safe, no setState after unmount) ── */
  const fetchStatus = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const res = await api.get<ShippingStatus>(`/shipping/status/${jobId}`, undefined, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return null;
      if (res?.data) {
        setStatus(res.data);
        return res.data;
      }
      return null;
    } catch {
      // Not started yet / aborted — use props
      return null;
    }
  }, [jobId]);

  /* ── Render route on map ── */
  const renderRoute = useCallback((L: typeof LType, map: LType.Map, st: ShippingStatus) => {
    // Clear existing
    markersRef.current.forEach((m) => m.remove());
    markersRef.current = [];
    polylineRef.current?.remove();
    truckMarkerRef.current?.remove();

    if (!st.waypoints || st.waypoints.length === 0) return;

    const latLngs: [number, number][] = st.waypoints.map((wp) => [wp.lat, wp.lon]);

    // Origin marker — shows EXACT user address
    const oAddr = st.origin?.address || originAddress || "مبدأ";
    const originIcon = L.divIcon({
      className: "",
      html: `<div style="background:#16a34a;color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-size:16px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35)">📍</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });
    const m1 = L.marker(latLngs[0], { icon: originIcon })
      .addTo(map)
      .bindPopup(`<div dir="rtl" style="font-family:Vazirmatn,Tahoma;text-align:right"><b>🟢 مبدأ</b><br/>${oAddr}</div>`);
    markersRef.current.push(m1);

    // Destination marker — shows EXACT user address
    const dAddr = st.destination?.address || destAddress || "مقصد";
    const destIcon = L.divIcon({
      className: "",
      html: `<div style="background:#dc2626;color:#fff;border-radius:50%;width:32px;height:32px;display:flex;align-items:center;justify-content:center;font-size:16px;border:2px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35)">🏁</div>`,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });
    const lastPt = latLngs[latLngs.length - 1];
    const m2 = L.marker(lastPt, { icon: destIcon })
      .addTo(map)
      .bindPopup(`<div dir="rtl" style="font-family:Vazirmatn,Tahoma;text-align:right"><b>🔴 مقصد</b><br/>${dAddr}</div>`);
    markersRef.current.push(m2);

    // Planned route polyline. These points are not GPS evidence.
    const poly = L.polyline(latLngs, {
      color: "#64748b",
      weight: 4,
      opacity: 0.65,
      dashArray: "8 6",
    }).addTo(map);
    polylineRef.current = poly;

    // Actual evidence points, when present, are rendered separately.
    const actualPoints = st.gps_list
      .filter((item): item is { Latitude: number; Longitude: number } => {
        if (!item || typeof item !== "object") return false;
        const point = item as Record<string, unknown>;
        return typeof point.Latitude === "number" && typeof point.Longitude === "number";
      })
      .map((point) => [point.Latitude, point.Longitude] as [number, number]);
    if (actualPoints.length > 1) {
      L.polyline(actualPoints, { color: "#0891b2", weight: 5, opacity: 0.9 }).addTo(map);
    }

    // Truck marker at current position
    const currentIdx = Math.min(st.current_step, st.waypoints.length - 1);
    const currentWp = st.waypoints[currentIdx];
    const truckIcon = L.divIcon({
      className: "",
      html: `<div style="background:#f59e0b;color:#fff;border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;font-size:20px;border:3px solid #fff;box-shadow:0 3px 10px rgba(0,0,0,.4)">🚚</div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
    });
    const truck = L.marker([currentWp.lat, currentWp.lon], { icon: truckIcon, zIndexOffset: 1000 })
      .addTo(map)
      .bindPopup(
        `<div dir="rtl" style="font-family:Vazirmatn,Tahoma;text-align:right">` +
          `<b>🚚 موقعیت فعلی</b><br/>` +
          `مسافت طی‌شده: ${st.traveled_km.toFixed(1)} کیلومتر<br/>` +
          `پیشرفت: ${st.progress_pct.toFixed(0)}%</div>`
      );
    truckMarkerRef.current = truck;
    markersRef.current.push(truck);

    // Planned waypoint dots (not telemetry)
    st.waypoints.forEach((wp, i) => {
      if (i === 0 || i === st.waypoints.length - 1) return; // skip origin/dest
      const visited = i <= st.current_step;
      const color = visited ? "#16a34a" : "#9ca3af";
      const wpIcon = L.divIcon({
        className: "",
        html: `<div style="background:${color};border-radius:50%;width:10px;height:10px;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.3)"></div>`,
        iconSize: [10, 10],
        iconAnchor: [5, 5],
      });
      const wpMarker = L.marker([wp.lat, wp.lon], { icon: wpIcon })
        .addTo(map)
        .bindPopup(
          `<div dir="rtl" style="font-family:Vazirmatn,Tahoma;text-align:right">` +
            `<b>نقطه ${i}</b><br/>` +
            `فاصله: ${wp.cum_km.toFixed(1)} کیلومتر<br/>` +
            `سرعت: ${wp.speed.toFixed(0)} کیلومتر/ساعت</div>`
        );
      markersRef.current.push(wpMarker);
    });

    map.fitBounds(poly.getBounds(), { padding: [50, 50] });
  }, [destAddress, originAddress]);

  /* ── Initialize Leaflet map ── */
  useEffect(() => {
    let isMounted = true;

    async function initMap() {
      if (typeof window === "undefined" || !mapRef.current || leafletMap.current) return;

      const L = (await import("leaflet")).default;
      if (!isMounted || !mapRef.current || leafletMap.current) return;

      const cLat = originLat ?? 35.6892;
      const cLng = originLng ?? 51.389;

      const map = L.map(mapRef.current).setView([cLat, cLng], 7);
      leafletMap.current = map;

      const addTileLayer = (url: string, maxZoom = 20) => {
        tileLayerRef.current?.remove();
        tileErrors.current = 0;
        const layer = L.tileLayer(url, {
          subdomains: "abcd",
          maxZoom,
          attribution: "© OpenStreetMap contributors, © CARTO",
        });
        // Real fallback: voyager (CARTO, unfiltered) -> dark_all -> OSM.
        layer.on("tileerror", () => {
          if (tileLayerRef.current !== layer) return;
          tileErrors.current += 1;
          if (tileErrors.current < 4) return;
          const order = [
            "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
            "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
          ];
          const next = order[order.indexOf(url) + 1];
          if (next && leafletMap.current === map) addTileLayer(next, 19);
        });
        layer.addTo(map);
        tileLayerRef.current = layer;
      };
      addTileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png");

      // Staged size recalculation to prevent blank/grey tiles on conditional mount.
      [50, 200, 500].forEach((delayMs) => {
        setTimeout(() => {
          if (isMounted && leafletMap.current) {
            leafletMap.current.invalidateSize();
          }
        }, delayMs);
      });

      // Load existing status
      const st = await fetchStatus();
      if (st && isMounted) {
        renderRoute(L, map, st);
      } else if (originLat && originLng && destLat && destLng) {
        // Render basic origin/dest markers from props
        const originIcon = L.divIcon({
          className: "",
          html: `<div style="background:#16a34a;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3)">📍</div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });
        const destIcon = L.divIcon({
          className: "",
          html: `<div style="background:#dc2626;color:#fff;border-radius:50%;width:28px;height:28px;display:flex;align-items:center;justify-content:center;font-size:14px;border:2px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.3)">🏁</div>`,
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });

        const m1 = L.marker([originLat, originLng], { icon: originIcon })
          .addTo(map)
          .bindPopup(`<b>مبدأ</b><br/>${originAddress || "نقطه شروع"}`);
        const m2 = L.marker([destLat, destLng], { icon: destIcon })
          .addTo(map)
          .bindPopup(`<b>مقصد</b><br/>${destAddress || "نقطه پایان"}`);
        markersRef.current = [m1, m2];

        L.polyline(
          [
            [originLat, originLng],
            [destLat, destLng],
          ],
          { color: "#6366f1", weight: 3, dashArray: "10 6", opacity: 0.6 }
        ).addTo(map);

        map.fitBounds([
          [originLat, originLng],
          [destLat, destLng],
        ], { padding: [50, 50] });
      }
    }

    initMap();

    // Attach debounced ResizeObserver to auto-adjust when container resizes.
    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && mapRef.current) {
      resizeObserver = new ResizeObserver(() => {
        scheduleInvalidate(120);
      });
      resizeObserver.observe(mapRef.current);
    }

    return () => {
      isMounted = false;
      abortRef.current?.abort();
      if (resizeTimer.current) clearTimeout(resizeTimer.current);
      resizeObserver?.disconnect();
      tileLayerRef.current = null;
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }
      markersRef.current = [];
      polylineRef.current = null;
      truckMarkerRef.current = null;
    };
  }, [jobId, originLat, originLng, destLat, destLng, originAddress, destAddress, fetchStatus, renderRoute, scheduleInvalidate]);

  /* ── Actions ── */

  const handleStart = async () => {
    if (!docNo) {
      toast.error("شماره سند بارنامه مشخص نیست");
      return;
    }
    setLoading(true);
    try {
      const latitude = originLat ?? status?.origin?.lat;
      const longitude = originLng ?? status?.origin?.lng;
      if (latitude == null || longitude == null) {
        throw new Error("مختصات مبدأ در بارنامه ثبت نشده است");
      }
      await api.post("/shipping/start", {
        job_id: jobId,
        doc_no: docNo,
        latitude,
        longitude,
        altitude: 0,
        speed: 0,
      });
      toast.success("✅ حمل شروع شد");
      const st = await fetchStatus();
      if (st && leafletMap.current) {
        const L = (await import("leaflet")).default;
        renderRoute(L, leafletMap.current, st);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "خطا در شروع حمل";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleFinish = async () => {
    setLoading(true);
    try {
      const measuredDistance = Number(measuredDistanceKm);
      if (!Number.isFinite(measuredDistance) || measuredDistance <= 0) {
        throw new Error("مسافت اندازه‌گیری‌شده را وارد کنید");
      }
      const latitude = destLat ?? status?.destination?.lat;
      const longitude = destLng ?? status?.destination?.lng;
      if (latitude == null || longitude == null) {
        throw new Error("مختصات مقصد در بارنامه ثبت نشده است");
      }
      await api.post("/shipping/finish", {
        job_id: jobId,
        latitude,
        longitude,
        altitude: 0,
        speed: 0,
        measured_distance_km: measuredDistance,
      });
      toast.success("✅ حمل با موفقیت پایان یافت");
      const st = await fetchStatus();
      if (st && leafletMap.current) {
        const L = (await import("leaflet")).default;
        renderRoute(L, leafletMap.current, st);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "خطا در پایان حمل";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  /* ── Render ── */
  const isStarted = status?.status === "in_transit";
  const isDelivered = status?.status === "delivered";

  return (
    <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-l from-blue-50 to-indigo-50 dark:from-gray-800 dark:to-gray-750 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center gap-2">
          <TruckIcon className="h-5 w-5 text-blue-600 dark:text-blue-400" />
          <h3 className="text-sm font-semibold text-gray-800 dark:text-gray-200">
            نقشه مسیر حمل GPS
          </h3>
        </div>

        {status && (
          <div className="flex items-center gap-2 text-xs">
            <span
              className={`px-2 py-1 rounded-full font-medium ${
                isDelivered
                  ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                  : isStarted
                    ? "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
                    : "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400"
              }`}
            >
              {isDelivered ? "تحویل شده ✅" : isStarted ? "در حال حمل 🚚" : "آماده شروع"}
            </span>
            {status.distance_km > 0 && (
              <span className="text-gray-600 dark:text-gray-300 font-medium">
                {status.distance_km.toFixed(0)} کیلومتر
              </span>
            )}
            {status.estimated_duration_text && (
              <span className="text-blue-600 dark:text-blue-400 font-medium bg-blue-50 dark:bg-blue-900/30 px-2 py-0.5 rounded">
                ⏱ {status.estimated_duration_text}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Address info bar */}
      <div className="flex flex-col sm:flex-row gap-2 px-4 py-2 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-100 dark:border-gray-700 text-xs">
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-green-500 shrink-0" />
          <span className="text-gray-600 dark:text-gray-400">مبدأ:</span>
          <span className="font-medium text-gray-800 dark:text-gray-200">
            {status?.origin?.address || originAddress || "—"}
          </span>
        </div>
        <span className="hidden sm:inline text-gray-300 dark:text-gray-600">←</span>
        <div className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-full bg-red-500 shrink-0" />
          <span className="text-gray-600 dark:text-gray-400">مقصد:</span>
          <span className="font-medium text-gray-800 dark:text-gray-200">
            {status?.destination?.address || destAddress || "—"}
          </span>
        </div>
      </div>

      {/* Map container */}
      <div ref={mapRef} className="w-full h-[350px] sm:h-[400px]" />

      {/* Progress bar */}
      {status && status.status !== "not_started" && (
        <div className="px-4 py-2 border-t border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
            <div className="flex items-center gap-2">
              <span>پیشرفت: {(status.progress_pct ?? 0).toFixed(0)}%</span>
              {status.remaining_duration_text && !isDelivered && (
                <span className="text-amber-600 dark:text-amber-400 text-[11px]">
                  (زمان باقی‌مانده: {status.remaining_duration_text})
                </span>
              )}
            </div>
            <span>
              {(status.traveled_km ?? 0).toFixed(1)} / {(status.distance_km ?? 0).toFixed(1)} کیلومتر
            </span>
          </div>
          <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
            <div
              className="bg-gradient-to-l from-blue-500 to-indigo-500 h-2 rounded-full transition-all duration-700"
              style={{ width: `${Math.min(100, status.progress_pct ?? 0)}%` }}
            />
          </div>
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap gap-2 p-3 border-t border-gray-100 dark:border-gray-700">
        {!isStarted && !isDelivered && (
          <>
            <button
              onClick={handleStart}
              disabled={loading || !docNo}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
            >
              <PlayIcon className="h-4 w-4" />
              شروع حمل
            </button>
          </>
        )}

        {isStarted && (
          <>
            <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300">
              <span>مسافت اندازه‌گیری‌شده (km)</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                inputMode="decimal"
                value={measuredDistanceKm}
                onChange={(event) => setMeasuredDistanceKm(event.target.value)}
                className="w-28 rounded-md border border-gray-300 bg-white px-2 py-1 text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                aria-label="مسافت اندازه‌گیری‌شده بر حسب کیلومتر"
              />
            </label>
            <button
              onClick={handleFinish}
              disabled={loading || !measuredDistanceKm}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-medium disabled:opacity-50 transition-colors"
            >
              <StopIcon className="h-4 w-4" />
              پایان حمل
            </button>
          </>
        )}

        {isDelivered && (
          <div className="flex items-center gap-1.5 px-3 py-1.5 bg-green-100 dark:bg-green-900/20 text-green-700 dark:text-green-400 rounded-lg text-xs font-medium">
            <CheckCircleIcon className="h-4 w-4" />
            حمل با موفقیت تحویل شد
          </div>
        )}

        <button
          onClick={async () => {
            const st = await fetchStatus();
            if (st && leafletMap.current) {
              const L = (await import("leaflet")).default;
              renderRoute(L, leafletMap.current, st);
            }
            toast.success("نقشه به‌روزرسانی شد");
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 hover:bg-gray-200 dark:bg-gray-700 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg text-xs font-medium transition-colors mr-auto"
        >
          <ArrowPathIcon className="h-3.5 w-3.5" />
          بروزرسانی
        </button>
      </div>
    </div>
  );
});

export default ShippingRouteMap;
