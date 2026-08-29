"use client";

import { memo, useEffect, useRef, useState } from "react";
import { MapPinIcon, ArrowPathIcon, GlobeAsiaAustraliaIcon } from "@heroicons/react/24/outline";
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

export const LocationMapPicker = memo(function LocationMapPicker({
  label,
  initialLat = 35.6892,
  initialLng = 51.3890,
  onLocationSelected,
  onClose,
}: LocationMapPickerProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const leafletMap = useRef<LType.Map | null>(null);
  const markerRef = useRef<LType.Marker | null>(null);
  const geocodeControllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(false);

  const [loadingGeocode, setLoadingGeocode] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lng: number }>({
    lat: initialLat,
    lng: initialLng,
  });
  const [resolvedAddress, setResolvedAddress] = useState<string>("");

  useEffect(() => {
    let isMounted = true;
    mountedRef.current = true;

    async function initLeaflet() {
      if (typeof window === "undefined" || !mapRef.current || leafletMap.current) return;

      try {
        const L = (await import("leaflet")).default;

        if (!isMounted || !mapRef.current || leafletMap.current) return;

        const map = L.map(mapRef.current).setView([initialLat, initialLng], 12);
        leafletMap.current = map;

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "© OpenStreetMap",
        }).addTo(map);

        const pinIcon = L.divIcon({
          className: "custom-leaflet-marker",
          html: '<div class="custom-leaflet-marker-dot"></div>',
          iconSize: [24, 24],
          iconAnchor: [12, 12],
        });

        const marker = L.marker([initialLat, initialLng], {
          draggable: true,
          icon: pinIcon,
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
      } catch (err) {
        if (process.env.NODE_ENV !== "production") {
          console.error("Failed to load Leaflet:", err);
        }
      }
    }

    initLeaflet();

    return () => {
      isMounted = false;
      mountedRef.current = false;
      geocodeControllerRef.current?.abort();
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleGeocode = async (lat: number, lng: number) => {
    geocodeControllerRef.current?.abort();
    const controller = new AbortController();
    geocodeControllerRef.current = controller;
    setSelectedCoords({ lat, lng });
    setResolvedAddress("");
    setLoadingGeocode(true);

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
  };

  const handleMyPosition = () => {
    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lat = pos.coords.latitude;
          const lng = pos.coords.longitude;
          if (mountedRef.current && leafletMap.current && markerRef.current) {
            leafletMap.current.setView([lat, lng], 14);
            markerRef.current.setLatLng([lat, lng]);
            handleGeocode(lat, lng);
          }
        },
        () => {
          toast.error("دسترسی به موقعیت جغرافیایی یافت نشد");
        }
      );
    } else {
      toast.error("مرورگر از موقعیت جغرافیایی پشتیبانی نمی‌کند");
    }
  };

  return (
    <div className="rounded-2xl bg-slate-900 border border-white/10 p-4 shadow-2xl space-y-3 mb-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-bold text-white">
          <MapPinIcon className="h-5 w-5 text-cyan-400" />
          <span>انتخاب روی نقشه — {label}</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleMyPosition}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs text-cyan-300 font-semibold border border-white/5 flex items-center gap-1 transition-all"
          >
            <GlobeAsiaAustraliaIcon className="h-4 w-4" />
            <span>موقعیت من</span>
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="text-xs text-slate-400 hover:text-white px-2 py-1"
            >
              بستن
            </button>
          )}
        </div>
      </div>

      <div className="relative w-full h-72 rounded-xl overflow-hidden border border-white/10 shadow-inner">
        <div ref={mapRef} className="w-full h-full z-0" />
        {loadingGeocode && (
          <div className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm z-10 flex items-center justify-center gap-2 text-cyan-400 text-xs font-bold">
            <ArrowPathIcon className="h-5 w-5 animate-spin" />
            <span>در حال دریافت آدرس پین...</span>
          </div>
        )}
      </div>

      {resolvedAddress && (
        <div className="p-3 rounded-xl bg-slate-950/80 border border-white/5 text-xs text-slate-300 flex items-center justify-between">
          <span className="truncate">{resolvedAddress}</span>
          <span className="text-[10px] font-mono text-cyan-400 shrink-0 me-2">
            {selectedCoords.lat.toFixed(4)}, {selectedCoords.lng.toFixed(4)}
          </span>
        </div>
      )}
    </div>
  );
});
