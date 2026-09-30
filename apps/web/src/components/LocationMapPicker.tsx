"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import {
  MapPinIcon,
  ArrowPathIcon,
  GlobeAsiaAustraliaIcon,
  SunIcon,
  MoonIcon,
  ArrowsPointingInIcon,
} from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import type * as LType from "leaflet";
import { api } from "@/lib/api";

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

const TILE_SERVERS = {
  google: {
    name: "نقشه خیابان‌ها (گوگل)",
    url: "https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}",
    subdomains: "0123",
    attribution: '&copy; Google Maps',
    maxZoom: 20,
  },
  voyager: {
    name: "نقشه روشن (Voyager)",
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">CARTO</a>',
    maxZoom: 20,
  },
  dark: {
    name: "نقشه تیره (Dark Matter)",
    url: "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
    subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">CARTO</a>',
    maxZoom: 20,
  },
  osm: {
    name: "OpenStreetMap",
    url: "https://tile.openstreetmap.de/{z}/{x}/{y}.png",
    subdomains: "",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    maxZoom: 19,
  },
};

export const LocationMapPicker = memo(function LocationMapPicker({
  label,
  initialLat = 35.6892,
  initialLng = 51.3890,
  onLocationSelected,
  onClose,
}: LocationMapPickerProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<LType.Map | null>(null);
  const currentTileLayer = useRef<LType.TileLayer | null>(null);
  const markerRef = useRef<LType.Marker | null>(null);
  const geocodeControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);

  const [mapTheme, setMapTheme] = useState<"google" | "voyager" | "dark" | "osm">("google");
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
      onLocationSelected({
        province: "",
        city: "",
        district: "",
        address: "",
        lat,
        lng,
      });

      try {
        const res = await api.get<{
          province: string;
          city: string;
          district: string;
          address: string;
        }>(`/api/v1/locations/reverse-geocode?lat=${lat}&lng=${lng}`, undefined, { signal: controller.signal });

        if (controller.signal.aborted || !mountedRef.current || geocodeControllerRef.current !== controller) return;
        setLoadingGeocode(false);

        if (res.success && res.data) {
          const { province, city, district, address } = res.data;
          setResolvedAddress(address || `${province} - ${city}`);
          // Enrichment second call overwrites the provisional address only.
          onLocationSelected({
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
    [onLocationSelected]
  );

  // Synchronize when parent updates coordinates (e.g. user selected city from dropdown or favorite location)
  useEffect(() => {
    if (!mountedRef.current || !leafletMap.current || !markerRef.current) return;
    if (initialLat != null && initialLng != null) {
      const cur = markerRef.current.getLatLng();
      const dist = Math.abs(cur.lat - initialLat) + Math.abs(cur.lng - initialLng);
      if (dist > 0.0001) {
        markerRef.current.setLatLng([initialLat, initialLng]);
        leafletMap.current.setView([initialLat, initialLng], Math.max(leafletMap.current.getZoom(), 13), {
          animate: true,
        });
        setSelectedCoords({ lat: initialLat, lng: initialLng });
        leafletMap.current.invalidateSize();
      }
    }
  }, [initialLat, initialLng]);

  // Tile fallback chain: google -> voyager -> dark -> osm
  const tileErrorCount = useRef(0);
  const applyTileLayer = useCallback(
    (L: typeof LType, map: LType.Map, theme: "google" | "voyager" | "dark" | "osm" = "google") => {
      if (currentTileLayer.current) {
        currentTileLayer.current.remove();
        currentTileLayer.current = null;
      }
      tileErrorCount.current = 0;

      const cfg = TILE_SERVERS[theme];
      const layer = L.tileLayer(cfg.url, {
        subdomains: cfg.subdomains,
        maxZoom: cfg.maxZoom,
        attribution: cfg.attribution,
      });

      // Real automatic fallback on sustained tile errors (sanctions / filtering).
      layer.on("tileerror", () => {
        if (layer !== currentTileLayer.current) return;
        tileErrorCount.current += 1;
        if (tileErrorCount.current < 3) return;
        const order: Array<"google" | "voyager" | "dark" | "osm"> = ["google", "voyager", "dark", "osm"];
        const next = order[order.indexOf(theme) + 1] || order[0];
        if (!next || next === theme) return;
        if (process.env.NODE_ENV !== "production") {
          console.warn(`Tile layer "${theme}" failing, falling back to "${next}"`);
        }
        setTimeout(() => {
          if (currentTileLayer.current === layer && leafletMap.current === map) {
            applyTileLayer(L, map, next);
          }
        }, 200);
      });

      layer.addTo(map);
      currentTileLayer.current = layer;
    },
    []
  );

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

        applyTileLayer(L, map, mapTheme);

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
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }
      markerRef.current = null;
      currentTileLayer.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleTheme = async () => {
    const order: Array<"google" | "voyager" | "dark" | "osm"> = ["google", "voyager", "dark", "osm"];
    const newTheme = order[(order.indexOf(mapTheme) + 1) % order.length];
    setMapTheme(newTheme);
    if (leafletMap.current) {
      const L = (await import("leaflet")).default;
      applyTileLayer(L, leafletMap.current, newTheme);
      leafletMap.current.invalidateSize();
    }
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
      if (window.location.protocol !== "https:" && window.location.hostname !== "localhost") {
        toast("درخواست GPS ارسال شد. (در ارتباط غیر HTTPS تایید مرورگر لازم است)", {
          icon: "📍",
          duration: 3500,
        });
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
            aria-label={`تغییر حالت نقشه: ${TILE_SERVERS[mapTheme]?.name || mapTheme}`}
            title={`تغییر حالت نقشه (${TILE_SERVERS[mapTheme]?.name})`}
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-white/5 transition-colors min-h-[38px] min-w-[38px] flex items-center justify-center"
          >
            {mapTheme === "dark" ? (
              <MoonIcon className="h-4 w-4 text-cyan-400" />
            ) : mapTheme === "google" ? (
              <GlobeAsiaAustraliaIcon className="h-4 w-4 text-emerald-400" />
            ) : (
              <SunIcon className="h-4 w-4 text-amber-400" />
            )}
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
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm z-10 flex items-center justify-center gap-2 text-cyan-400 text-xs font-bold pointer-events-none"
          >
            <ArrowPathIcon className="h-5 w-5 animate-spin" aria-hidden="true" />
            <span>در حال دریافت آدرس پین...</span>
          </div>
        )}
      </div>

      {/* Instruction hint */}
      <p className="text-[11px] text-slate-400 leading-relaxed">
        💡 برای تغییر موقعیت در موبایل یا رایانه، روی هر نقطه از نقشه لمس/کلیک کنید یا پین را بکشید — مختصات فوراً ذخیره می‌شود و آدرس تکمیل خواهد شد.
      </p>

      {/* Resolved address banner */}
      {resolvedAddress && (
        <div
          role="status"
          aria-live="polite"
          className="p-3 rounded-xl bg-slate-950/80 border border-white/5 text-xs text-slate-300 flex items-center justify-between gap-3"
        >
          <span className="truncate">{resolvedAddress}</span>
          <span className="text-[10px] font-mono text-cyan-400 shrink-0 me-2" dir="ltr">
            {selectedCoords.lat.toFixed(5)}, {selectedCoords.lng.toFixed(5)}
          </span>
        </div>
      )}
    </div>
  );
});

export default LocationMapPicker;
