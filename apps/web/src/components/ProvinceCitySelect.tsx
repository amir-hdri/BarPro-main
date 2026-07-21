"use client";

import { memo, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MagnifyingGlassIcon, ChevronDownIcon } from "@heroicons/react/24/outline";

interface City {
  name: string;
  lat: float;
  lng: float;
}

interface Province {
  name: string;
  capital: string;
  lat: float;
  lng: float;
  cities_count: number;
}

interface ProvinceCitySelectProps {
  provinceValue: string;
  cityValue: string;
  onProvinceChange: (province: string) => void;
  onCityChange: (city: string, coords?: { lat: number; lng: number }) => void;
  provinceError?: string;
  cityError?: string;
}

export const ProvinceCitySelect = memo(function ProvinceCitySelect({
  provinceValue,
  cityValue,
  onProvinceChange,
  onCityChange,
  provinceError,
  cityError,
}: ProvinceCitySelectProps) {
  const [provinces, setProvinces] = useState<Province[]>([]);
  const [cities, setCities] = useState<City[]>([]);
  const [loadingProvinces, setLoadingProvinces] = useState(true);
  const [loadingCities, setLoadingCities] = useState(false);

  // لود اولیه استان‌ها
  useEffect(() => {
    async function fetchProvinces() {
      setLoadingProvinces(true);
      const res = await api.get<Province[]>("/api/v1/locations/provinces");
      if (res.success && res.data) {
        setProvinces(res.data);
      }
      setLoadingProvinces(false);
    }
    fetchProvinces();
  }, []);

  // لود شهرهای استان انتخاب شده
  useEffect(() => {
    async function fetchCities() {
      if (!provinceValue) {
        setCities([]);
        return;
      }
      setLoadingCities(true);
      const res = await api.get<City[]>(`/api/v1/locations/cities?province=${encodeURIComponent(provinceValue)}`);
      if (res.success && res.data) {
        setCities(res.data);
      }
      setLoadingCities(false);
    }
    fetchCities();
  }, [provinceValue]);

  const handleProvinceSelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    onProvinceChange(val);
    onCityChange(""); // ریست کردن شهر موقع تغییر استان
  };

  const handleCitySelect = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const val = e.target.value;
    const selectedCity = cities.find((c) => c.name === val);
    onCityChange(
      val,
      selectedCity ? { lat: selectedCity.lat, lng: selectedCity.lng } : undefined
    );
  };

  return (
    <div className="grid gap-5 sm:grid-cols-2">
      <div>
        <label className="block text-sm font-semibold text-slate-200 mb-2">
          استان <span className="text-rose-500 text-xs">*</span>
        </label>
        <div className="relative">
          <select
            value={provinceValue}
            onChange={handleProvinceSelect}
            className={`field appearance-none pr-4 pl-10 ${provinceError ? "error" : ""}`}
            disabled={loadingProvinces}
          >
            <option value="">انتخاب استان...</option>
            {provinces.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} ({p.cities_count} شهر)
              </option>
            ))}
          </select>
          <ChevronDownIcon className="absolute left-3 top-3.5 h-4 w-4 text-slate-400 pointer-events-none" />
        </div>
        {provinceError && <span className="mt-1 text-xs text-rose-500 font-medium block">{provinceError}</span>}
      </div>

      <div>
        <label className="block text-sm font-semibold text-slate-200 mb-2">
          شهر <span className="text-rose-500 text-xs">*</span>
        </label>
        <div className="relative">
          <select
            value={cityValue}
            onChange={handleCitySelect}
            className={`field appearance-none pr-4 pl-10 ${cityError ? "error" : ""}`}
            disabled={!provinceValue || loadingCities}
          >
            <option value="">
              {!provinceValue ? "ابتدا استان را انتخاب کنید..." : loadingCities ? "در حال بارگذاری شهرها..." : "انتخاب شهر..."}
            </option>
            {cities.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
          <ChevronDownIcon className="absolute left-3 top-3.5 h-4 w-4 text-slate-400 pointer-events-none" />
        </div>
        {cityError && <span className="mt-1 text-xs text-rose-500 font-medium block">{cityError}</span>}
      </div>
    </div>
  );
});
