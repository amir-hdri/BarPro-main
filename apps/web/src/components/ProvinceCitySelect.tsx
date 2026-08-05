"use client";

import { memo, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { ChevronDownIcon } from "@heroicons/react/24/outline";

interface City {
  name: string;
  lat: number;
  lng: number;
}

interface Province {
  name: string;
  capital: string;
  lat: number;
  lng: number;
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
  const [provinceFetchError, setProvinceFetchError] = useState(false);
  const [cityFetchError, setCityFetchError] = useState(false);

  // لود اولیه استان‌ها
  const fetchProvinces = async () => {
    setLoadingProvinces(true);
    setProvinceFetchError(false);
    try {
      const res = await api.get<Province[]>("/api/v1/locations/provinces");
      if (res.success && res.data && res.data.length > 0) {
        setProvinces(res.data);
      } else {
        setProvinceFetchError(true);
      }
    } catch {
      setProvinceFetchError(true);
    } finally {
      setLoadingProvinces(false);
    }
  };

  useEffect(() => {
    fetchProvinces();
  }, []);

  // لود شهرهای استان انتخاب شده
  const fetchCities = async () => {
    if (!provinceValue) {
      setCities([]);
      setCityFetchError(false);
      return;
    }
    setLoadingCities(true);
    setCityFetchError(false);
    try {
      const res = await api.get<City[]>(`/api/v1/locations/cities?province=${encodeURIComponent(provinceValue)}`);
      if (res.success && res.data && res.data.length > 0) {
        setCities(res.data);
      } else {
        setCityFetchError(true);
      }
    } catch {
      setCityFetchError(true);
    } finally {
      setLoadingCities(false);
    }
  };

  useEffect(() => {
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
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-semibold text-slate-200">
            استان <span className="text-rose-500 text-xs">*</span>
          </label>
          {provinceFetchError && (
            <button
              type="button"
              onClick={fetchProvinces}
              className="text-xs text-amber-400 hover:text-amber-300 font-bold underline"
            >
              تلاش مجدد
            </button>
          )}
        </div>
        <div className="relative">
          <select
            value={provinceValue}
            onChange={handleProvinceSelect}
            className={`field appearance-none pr-4 pl-10 ${provinceError || provinceFetchError ? "error" : ""}`}
            disabled={loadingProvinces}
          >
            <option value="">
              {loadingProvinces
                ? "در حال بارگذاری استان‌ها..."
                : provinceFetchError
                ? "ارتباط با سرور برقرار نشد (کلیک جهت تلاش مجدد)"
                : "انتخاب استان..."}
            </option>
            {provinces.map((p) => (
              <option key={p.name} value={p.name}>
                {p.name} ({p.cities_count} شهر)
              </option>
            ))}
          </select>
          <ChevronDownIcon className="absolute left-3 top-3.5 h-4 w-4 text-slate-400 pointer-events-none" />
        </div>
        {provinceFetchError && (
          <span className="mt-1 text-xs text-rose-400 font-medium block">
            خطا در دریافت لیست استان‌ها. لطفاً روی «تلاش مجدد» کلیک کنید.
          </span>
        )}
        {provinceError && !provinceFetchError && (
          <span className="mt-1 text-xs text-rose-500 font-medium block">{provinceError}</span>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="block text-sm font-semibold text-slate-200">
            شهر <span className="text-rose-500 text-xs">*</span>
          </label>
          {cityFetchError && (
            <button
              type="button"
              onClick={fetchCities}
              className="text-xs text-amber-400 hover:text-amber-300 font-bold underline"
            >
              تلاش مجدد
            </button>
          )}
        </div>
        <div className="relative">
          <select
            value={cityValue}
            onChange={handleCitySelect}
            className={`field appearance-none pr-4 pl-10 ${cityError || cityFetchError ? "error" : ""}`}
            disabled={!provinceValue || loadingCities}
          >
            <option value="">
              {!provinceValue
                ? "ابتدا استان را انتخاب کنید..."
                : loadingCities
                ? "در حال بارگذاری شهرها..."
                : cityFetchError
                ? "ارتباط با سرور برقرار نشد (کلیک جهت تلاش مجدد)"
                : "انتخاب شهر..."}
            </option>
            {cities.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}
              </option>
            ))}
          </select>
          <ChevronDownIcon className="absolute left-3 top-3.5 h-4 w-4 text-slate-400 pointer-events-none" />
        </div>
        {cityFetchError && (
          <span className="mt-1 text-xs text-rose-400 font-medium block">
            خطا در دریافت لیست شهرهای استان. لطفاً روی «تلاش مجدد» کلیک کنید.
          </span>
        )}
        {cityError && !cityFetchError && (
          <span className="mt-1 text-xs text-rose-500 font-medium block">{cityError}</span>
        )}
      </div>
    </div>
  );
});
