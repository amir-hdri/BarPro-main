"use client";

import { memo, useEffect, useRef, useState } from "react";
import { MapPinIcon, ArrowPathIcon, GlobeAsiaAustraliaIcon } from "@heroicons/react/24/outline";
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
  const leafletMap = useRef<any>(null);
  const markerRef = useRef<any>(null);

  const [loadingGeocode, setLoadingGeocode] = useState(false);
  const [selectedCoords, setSelectedCoords] = useState<{ lat: number; lng: number }>({
    lat: initialLat,
    lng: initialLng,
  });
  const [resolvedAddress, setResolvedAddress] = useState<string>("");

  useEffect(() => {
    // Dynamic Leaflet CSS and JS injection
    const cssId = "leaflet-css";
    if (!document.getElementById(cssId)) {
      const link = document.createElement("link");
      link.id = cssId;
      link.rel = "stylesheet";
      link.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(link);
    }

    const scriptId = "leaflet-js";
    let isMounted = true;

    const initMap = () => {
      const L = (window as any).L;
      if (!L || !mapRef.current || leafletMap.current) return;

      const map = L.map(mapRef.current).setView([initialLat, initialLng], 12);
      leafletMap.current = map;

      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
      }).addTo(map);

      // Custom Pin Icon
      const pinIcon = L.divIcon({
        className: "custom-leaflet-marker",
        html: `<div style="background:#06b6d4;width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 0 10px rgba(0,0,0,0.5);"></div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
      });

      const marker = L.marker([initialLat, initialLng], {
        draggable: true,
        icon: pinIcon,
      }).addTo(map);
      markerRef.current = marker;

      // Event on map click
      map.on("click", (e: any) => {
        const { lat, lng } = e.latlng;
        marker.setLatLng([lat, lng]);
        if (isMounted) handleGeocode(lat, lng);
      });

      // Event on marker dragend
      marker.on("dragend", (e: any) => {
        const { lat, lng } = e.target.getLatLng();
        if (isMounted) handleGeocode(lat, lng);
      });
    };

    if ((window as any).L) {
      initMap();
    } else if (!document.getElementById(scriptId)) {
      const script = document.createElement("script");
      script.id = scriptId;
      script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      script.onload = () => {
        if (isMounted) initMap();
      };
      document.body.appendChild(script);
    } else {
      const interval = setInterval(() => {
        if ((window as any).L) {
          clearInterval(interval);
          if (isMounted) initMap();
        }
      }, 200);
    }

    return () => {
      isMounted = false;
      if (leafletMap.current) {
        leafletMap.current.remove();
        leafletMap.current = null;
      }
    };
  }, []);

  const handleGeocode = async (lat: number, lng: number) => {
    setSelectedCoords({ lat, lng });
    setLoadingGeocode(true);

    const res = await api.get<{
      province: string;
      city: string;
      district: string;
      address: string;
    }>(`/api/v1/locations/reverse-geocode?lat=${lat}&lng=${lng}`);

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
          if (leafletMap.current && markerRef.current) {
            leafletMap.current.setView([lat, lng], 14);
            markerRef.current.setLatLng([lat, lng]);
            handleGeocode(lat, lng);
          }
        },
        () => {
          alert("دسترسی به موقعیت جغرافیایی یافت نشد");
        }
      );
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
          <span className="text-[10px] font-mono text-cyan-400 shrink-0 mr-2">
            {selectedCoords.lat.toFixed(4)}, {selectedCoords.lng.toFixed(4)}
          </span>
        </div>
      )}
    </div>
  );
});
