"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  MapPinIcon,
  ArrowPathIcon,
  GlobeAsiaAustraliaIcon,
  ArrowsPointingInIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import type * as LType from "leaflet";
import { api } from "@/lib/api";
import { createMapTiles, MAP_TILES, MAP_TILE_ORDER, type MapTheme, type MapTileStatus } from "@/lib/map-tiles";

interface LocationMapPickerProps {
  label: string;
  initialLat?: number;
  initialLng?: number;
  onLocationSelected: (location: {
    province: string;
    city: string;
    district: string;
    address: string;
    lat: number;
    lng: number;
  }) => void;
  onClose?: () => void;
}

export const LocationMapPicker = memo(function LocationMapPicker({
  label,
  initialLat = 35.6892,
  initialLng = 51.3890,
  onLocationSelected,
  onClose,
}: LocationMapPickerProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<LType.Map | null>(null);
  const tilesRef = useRef<ReturnType<typeof createMapTiles> | null>(null);
  const selectionCallbackRef = useRef(onLocationSelected);
  useEffect(() => { selectionCallbackRef.current = onLocationSelected; }, [onLocationSelected]);
  const markerRef = useRef<LType.Marker | null>(null);
  const geocodeControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);

  const [mapTheme, setMapTheme] = useState<MapTheme>("osm");
  const [tileStatus, setTileStatus] = useState<MapTileStatus>("loading");
  const [loadingGeocode, setLoadingGeocode] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lng: number }>({
    lat: initialLat,
    lng: initialLng,
  });
  const [resolvedAddress, setResolvedAddress] = useState<string>("");

  // Phase 2 fix: commit coordinates to parent IMMEDIATELY on map click,
  // then enrich address asynchronously. A reverse-geocode failure must never
  // drop the selected pin (previously parent never received coords on 500/
  // timeout, leaving UI pin ≠ form state).
  const handleGeocode = useCallback(
    async (lat: number, lng: number) => {
      geocodeControllerRef.current?.abort();
      const controller = new AbortController();
      geocodeControllerRef.current = controller;
      setSelectedCoords({ lat, lng });
      setResolvedAddress("");
      setLoadingGeocode(true);

      // Immediate commit with provisional (empty) address — parent state is
      // always correct even if geocoding fails.
      selectionCallbackRef.current({
        province: "",
        city: "",
        district: "",
        address: "",
        lat,
        lng,
      });

      try {
        const res = await api.get<{
          success?: boolean;
          province: string;
          city: string;
          district: string;
          address: string;
          is_approximate?: boolean;
          display_name?: string;
        }>(`/api/v1/locations/reverse-geocode?lat=${lat}&lng=${lng}`, undefined, { signal: controller.signal });

        if (controller.signal.aborted || !mountedRef.current || geocodeControllerRef.current !== controller) return;
        setLoadingGeocode(false);

        if (res.success && res.data && res.data.success !== false) {
          const { province, city, district, address } = res.data;
          setResolvedAddress(res.data.is_approximate
            ? `${res.data.display_name || city} — موقعیت تقریبی است؛ آدرس دقیق را وارد کنید.`
            : address || `${province} - ${city}`);
          // Enrichment second call overwrites the provisional address only.
          selectionCallbackRef.current({
            province,
            city,
            district,
            address: address || "",
            lat,
            lng,
          });
        } else {
          setResolvedAddress(`پین ثبت شد (${lat.toFixed(5)}, ${lng.toFixed(5)}) — آدرس یافت نشد`);
        }
      } catch {
        if (!controller.signal.aborted && mountedRef.current) {
          setLoadingGeocode(false);
          // Coordinates already committed above; only show hint banner.
          setResolvedAddress(`پین ثبت شد (${lat.toFixed(5)}, ${lng.toFixed(5)}) — خطای دریافت آدرس`);
        }
      }
    },
    []
  );

  // Synchronize when parent updates coordinates (e.g. user selected city from dropdown or favorite location)
  useEffect(() => {
    if (!mountedRef.current || !leafletMap.current || !markerRef.current) return;
    if (initialLat != null && initialLng != null) {
      const cur = markerRef.current.getLatLng();
      const dist = Math.abs(cur.lat - initialLat) + Math.abs(cur.lng - initialLng);
      if (dist > 0.0001) {
        geocodeControllerRef.current?.abort();
        setLoadingGeocode(false);
        setResolvedAddress("");
        markerRef.current.setLatLng([initialLat, initialLng]);
        leafletMap.current.setView([initialLat, initialLng], Math.max(leafletMap.current.getZoom(), 13), {
          animate: true,
        });
        setSelectedCoords({ lat: initialLat, lng: initialLng });
        leafletMap.current.invalidateSize();
      }
    }
  }, [initialLat, initialLng]);

  // Debounced invalidateSize
  const resizeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scheduleInvalidate = useCallback((delayMs = 120) => {
    if (resizeTimer.current) clearTimeout(resizeTimer.current);
    resizeTimer.current = setTimeout(() => {
      leafletMap.current?.invalidateSize();
    }, delayMs);
  }, []);

  useEffect(() => {
    let isMounted = true;
    mountedRef.current = true;

    async function initLeaflet() {
      if (typeof window === "undefined" || !mapRef.current || leafletMap.current) return;

      try {
        const L = (await import("leaflet")).default;
        if (!isMounted || !mapRef.current || leafletMap.current) return;

        const map = L.map(mapRef.current, {
          zoomControl: true,
          fadeAnimation: true,
          touchZoom: true,
          dragging: true,
        }).setView([initialLat, initialLng], 13);
        leafletMap.current = map;

        tilesRef.current = createMapTiles(L, map, (theme, state) => {
          if (isMounted) { setMapTheme(theme); setTileStatus(state); }
        });
        tilesRef.current.select();

        const pinIcon = L.divIcon({
          className: "custom-leaflet-marker",
          html: '<div class="custom-leaflet-marker-dot"></div>',
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        });

        const marker = L.marker([initialLat, initialLng], {
          draggable: true,
          icon: pinIcon,
          title: `پین ${label}`,
        }).addTo(map);
        markerRef.current = marker;

        map.on("click", (e: LType.LeafletMouseEvent) => {
          const { lat, lng } = e.latlng;
          marker.setLatLng([lat, lng]);
          if (isMounted) handleGeocode(lat, lng);
        });

        marker.on("dragend", (e: LType.LeafletEvent) => {
          const targetMarker = e.target as LType.Marker;
          const { lat, lng } = targetMarker.getLatLng();
          if (isMounted) handleGeocode(lat, lng);
        });

        // Staged size recalculation to prevent blank/grey tiles on mobile
        [50, 150, 300, 600, 1000].forEach((delayMs) => {
          setTimeout(() => {
            if (isMounted && leafletMap.current) {
              leafletMap.current.invalidateSize();
            }
          }, delayMs);
        });
      } catch (err) {
        if (isMounted) setTileStatus('unavailable');
        if (process.env.NODE_ENV !== "production") {
          console.error("Failed to load Leaflet:", err);
        }
      }
    }

    initLeaflet();

    // Attach debounced ResizeObserver to auto-adjust when modal or parent layout resizes
    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && mapRef.current) {
      resizeObserver = new ResizeObserver(() => {
        scheduleInvalidate(100);
      });
      resizeObserver.observe(mapRef.current);
    }

    const handleWindowResize = () => {
      if (mountedRef.current && leafletMap.current) {
        leafletMap.current.invalidateSize();
      }
    };
    window.addEventListener("resize", handleWindowResize);
    window.addEventListener("orientationchange", handleWindowResize);

    return () => {
      isMounted = false;
      mountedRef.current = false;
      if (resizeTimer.current) clearTimeout(resizeTimer.current);
      resizeObserver?.disconnect();
      window.removeEventListener("resize", handleWindowResize);
      window.removeEventListener("orientationchange", handleWindowResize);
      geocodeControllerRef.current?.abort();
      tilesRef.current?.dispose();
      tilesRef.current = null;
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleTheme = () => {
    tilesRef.current?.select(MAP_TILE_ORDER[(MAP_TILE_ORDER.indexOf(mapTheme) + 1) % MAP_TILE_ORDER.length]);
  };

  const handleCenter = () => {
    if (leafletMap.current && markerRef.current) {
      const { lat, lng } = selectedCoords;
      leafletMap.current.setView([lat, lng], 14, { animate: true });
      leafletMap.current.invalidateSize();
    }
  };

  const handleMyPosition = () => {
    if (typeof window !== "undefined" && navigator.geolocation) {
      if (!window.isSecureContext) {
        toast.error("موقعیت خودکار به اتصال امن HTTPS نیاز دارد؛ نقطه را روی نقشه انتخاب کنید.");
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          if (mountedRef.current && leafletMap.current && markerRef.current) {
            leafletMap.current.setView([lat, lng], 15, { animate: true });
            markerRef.current.setLatLng([lat, lng]);
            handleGeocode(lat, lng);
            setTimeout(() => {
              leafletMap.current?.invalidateSize();
            }, 200);
          }
        },
        () => {
          toast.error("دریافت موقعیت خودکار مقدور نشد — لطفاً موقعیت را مستقیماً روی نقشه لمس کنید");
        },
        { enableHighAccuracy: true, timeout: 8000 }
      );
    } else {
      toast.error("مرورگر از موقعیت جغرافیایی پشتیبانی نمی‌کند");
    }
  };

  return (
    <div
      role="region"
      aria-label={`نقشه تعاملی انتخاب موقعیت جغرافیایی ${label}`}
      className="rounded-2xl bg-slate-900 border border-white/10 p-4 shadow-2xl space-y-3 mb-6 transition-all"
    >
      {/* Header toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2 text-sm font-bold text-white">
          <MapPinIcon className="h-5 w-5 text-cyan-400 shrink-0" aria-hidden="true" />
          <span>انتخاب روی نقشه — {label}</span>
        </div>
        <div className="flex items-center gap-1.5 flex-wrap">
          <button
            type="button"
            onClick={toggleTheme}
            aria-label={`تغییر منبع نقشه: ${MAP_TILES[mapTheme]?.name || mapTheme}`}
            title={`تغییر منبع نقشه (${MAP_TILES[mapTheme]?.name})`}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-white/5 transition-colors min-h-[38px] min-w-[38px] flex items-center justify-center"
          >
            <GlobeAsiaAustraliaIcon className="h-4 w-4 text-cyan-400" />
          </button>

          <button
            type="button"
            onClick={handleCenter}
            aria-label="تنظیم مجدد به مرکز پین"
            title="تمرکز روی پین"
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-white/5 transition-colors min-h-[38px] min-w-[38px] flex items-center justify-center"
          >
            <ArrowsPointingInIcon className="h-4 w-4" />
          </button>

          <button
            type="button"
            onClick={handleMyPosition}
            aria-label="دریافت موقعیت فعلی از طریق GPS دستگاه"
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-cyan-300 font-semibold border border-white/5 flex items-center gap-1.5 transition-all min-h-[38px]"
          >
            <GlobeAsiaAustraliaIcon className="h-4 w-4" aria-hidden="true" />
            <span>موقعیت من</span>
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="بستن پنجره نقشه"
              className="text-xs text-slate-400 hover:text-white px-2.5 py-1.5 rounded-lg hover:bg-slate-800 min-h-[38px] transition-colors"
            >
              بستن
            </button>
          )}
        </div>
      </div>

      {/* Map display */}
      <div className="relative w-full h-72 sm:h-80 md:h-96 rounded-2xl overflow-hidden border border-white/10 shadow-inner bg-slate-950">
        <div ref={mapRef} className="w-full h-full z-0" tabIndex={0} aria-label="ناحیه نقشه قابل جابجایی" />
        {loadingGeocode && (
          <div
            role="status"
            aria-live="polite"
            className="absolute bottom-3 start-3 end-3 rounded-lg bg-white/95 px-3 py-2 z-[500] flex items-center gap-2 text-slate-800 text-xs font-bold pointer-events-none"
          >
            <ArrowPathIcon className="h-5 w-5 animate-spin" aria-hidden="true" />
            <span>در حال دریافت آدرس پین...</span>
          </div>
        )}
      </div>

      {tileStatus !== 'ready' && (
        <div role="status" aria-live="polite" className="flex flex-wrap items-center gap-3 text-xs text-amber-200">
          <span>{tileStatus === 'loading' ? 'در حال بارگذاری نقشه…' : 'تصویر نقشه دریافت نشد. اتصال اینترنت را بررسی کنید و دوباره تلاش کنید.'}</span>
          {tileStatus === 'unavailable' && <button type="button" className="min-h-11 rounded-lg border border-white/20 px-3" onClick={() => tilesRef.current?.select()}>تلاش دوباره</button>}
        </div>
      )}

      {/* Instruction hint */}
      <p className="text-[11px] text-slate-400 leading-relaxed">
        💡 برای تغییر موقعیت در موبایل یا رایانه، روی هر نقطه از نقشه لمس/کلیک کنید یا پین را بکشید — مختصات فوراً ذخیره می‌شود و در صورت دریافت آدرس، فیلدها تکمیل می‌شوند. آدرس دقیق را پیش از ادامه بررسی کنید. مسیر حرکت از نزدیک‌ترین خیابان قابل‌تردد محاسبه می‌شود و جابه‌جایی در نقشه حمل مشخص است.
      </p>

      {/* Resolved address banner */}
      {resolvedAddress && (
        <div
          role="status"
          aria-live="polite"
          className="p-3 rounded-xl bg-slate-950/80 border border-white/5 text-xs text-slate-300 flex flex-wrap items-center justify-between gap-3"
        >
          <span className="break-words">{resolvedAddress}</span>
          <span className="text-[10px] font-mono text-cyan-400 shrink-0 me-2" dir="ltr">
            {selectedCoords.lat.toFixed(5)}, {selectedCoords.lng.toFixed(5)}
          </span>
        </div>
      )}
    </div>
  );
});

export default LocationMapPicker;
