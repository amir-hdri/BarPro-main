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
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    subdomains: "abc",
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

  const [mapTheme, setMapTheme] = useState<"voyager" | "dark">("voyager");
  const [loadingGeocode, setLoadingGeocode] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lng: number }>({
    lat: initialLat,
    lng: initialLng,
  });
  const [resolvedAddress, setResolvedAddress] = useState<string>("");

  const handleGeocode = useCallback(
    async (lat: number, lng: number) => {
      geocodeControllerRef.current?.abort();
      const controller = new AbortController();
      geocodeControllerRef.current = controller;
      setSelectedCoords({ lat, lng });
      setResolvedAddress("");
      setLoadingGeocode(true);

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
          onLocationSelected({
            province,
            city,
            district,
            address: address || "",
            lat,
            lng,
          });
        }
      } catch {
        if (!controller.signal.aborted && mountedRef.current) {
          setLoadingGeocode(false);
        }
      }
    },
    [onLocationSelected]
  );

  // Tile fallback chain: voyager (default, CARTO, unfiltered) -> dark -> osm.
  // Switches layers for real after a burst of tile errors instead of only logging.
  const tileErrorCount = useRef(0);
  const applyTileLayer = useCallback(
    (L: typeof LType, map: LType.Map, theme: "voyager" | "dark" | "osm" = "voyager") => {
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
        if (tileErrorCount.current < 4) return;
        const order: Array<"voyager" | "dark" | "osm"> = ["voyager", "dark", "osm"];
        const next = order[order.indexOf(theme) + 1];
        if (!next) return;
        if (process.env.NODE_ENV !== "production") {
          console.warn(`Primary tile "${theme}" failing, falling back to "${next}"`);
        }
        // Defer so Leaflet finishes the current tile batch first.
        setTimeout(() => {
          if (currentTileLayer.current === layer && leafletMap.current === map) {
            applyTileLayer(L, map, next);
          }
        }, 300);
      });

      layer.addTo(map);
      currentTileLayer.current = layer;
    },
    []
  );

  // Debounced invalidateSize: ResizeObserver can fire in bursts during modal
  // open animations; a single trailing call avoids layout thrash and 0x0 grey tiles.
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

        // Staged size recalculation to prevent blank/grey tiles on conditional mount.
        // 50ms catches the first layout pass, 200ms the modal animation end,
        // 500ms a late font/layout shift.
        [50, 200, 500].forEach((delayMs) => {
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

    // Attach debounced ResizeObserver to auto-adjust when modal or parent layout resizes.
    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && mapRef.current) {
      resizeObserver = new ResizeObserver(() => {
        scheduleInvalidate(120);
      });
      resizeObserver.observe(mapRef.current);
    }

    return () => {
      isMounted = false;
      mountedRef.current = false;
      if (resizeTimer.current) clearTimeout(resizeTimer.current);
      resizeObserver?.disconnect();
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
    const newTheme = mapTheme === "voyager" ? "dark" : "voyager";
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
    if (navigator.geolocation) {
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
          toast.error("دسترسی به موقعیت جغرافیایی یافت نشد");
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
            aria-label={`تغییر حالت نقشه به ${mapTheme === "voyager" ? "تیره" : "روشن"}`}
            title="تغییر تم نقشه (روشن / تیره)"
            className="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-white/5 transition-colors min-h-[38px] min-w-[38px] flex items-center justify-center"
          >
            {mapTheme === "voyager" ? <MoonIcon className="h-4 w-4" /> : <SunIcon className="h-4 w-4 text-amber-400" />}
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
      <div className="relative w-full h-80 rounded-xl overflow-hidden border border-white/10 shadow-inner bg-slate-950">
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
        💡 روی نقشه کلیک کنید یا پین دایره‌ای را بکشید تا آدرس، استان و شهر به‌طور خودکار تنظیم شوند.
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
