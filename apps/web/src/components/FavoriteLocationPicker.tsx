"use client";

import { memo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookmarkIcon, PlusIcon, TrashIcon, CheckIcon } from "@heroicons/react/24/outline";
import toast from "react-hot-toast";
import { api } from "@/lib/api";

interface FavoriteLocation {
  id: number;
  title: string;
  province: string;
  city: string;
  district?: string;
  address: string;
  latitude?: number;
  longitude?: number;
  is_origin: boolean;
  is_destination: boolean;
}

interface FavoriteLocationPickerProps {
  mode: "origin" | "destination";
  currentProvince?: string;
  currentCity?: string;
  currentDistrict?: string;
  currentAddress?: string;
  currentLat?: number;
  currentLng?: number;
  onSelectFavorite: (fav: FavoriteLocation) => void;
}

export const FavoriteLocationPicker = memo(function FavoriteLocationPicker({
  mode,
  currentProvince,
  currentCity,
  currentDistrict,
  currentAddress,
  currentLat,
  currentLng,
  onSelectFavorite,
}: FavoriteLocationPickerProps) {
  const queryClient = useQueryClient();
  const { data: favorites = [], isLoading, isError, refetch } = useQuery({
    queryKey: ["location-favorites"],
    queryFn: async ({ signal }) => {
      const res = await api.get<FavoriteLocation[] | { data?: FavoriteLocation[] }>(
        "/api/v1/locations/favorites",
        undefined,
        { signal }
      );
      if (signal.aborted) return [];
      if (!res.success) throw new Error(res.error || "خطا در دریافت مکان‌های منتخب");
      if (!res.data) return [];
      if (Array.isArray(res.data)) return res.data;
      return Array.isArray(res.data.data) ? res.data.data : [];
    },
    staleTime: 60_000,
  });
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const handleSaveCurrent = async () => {
    if (!newTitle.trim() || !currentProvince || !currentCity || !currentAddress) {
      toast.error("لطفا ابتدا عنوان، استان، شهر و آدرس را تکمیل کنید.");
      return;
    }
    setSaving(true);
    const res = await api.post("/api/v1/locations/favorites", {
      title: newTitle.trim(),
      province: currentProvince,
      city: currentCity,
      district: currentDistrict || undefined,
      address: currentAddress,
      latitude: currentLat ?? undefined,
      longitude: currentLng ?? undefined,
      is_origin: mode === "origin",
      is_destination: mode === "destination",
    });
    setSaving(false);

    if (res.success) {
      toast.success("مکان منتخب با موفقیت ذخیره شد");
      setShowSaveModal(false);
      setNewTitle("");
      await queryClient.invalidateQueries({ queryKey: ["location-favorites"] });
    } else {
      toast.error(res.error || "خطا در ذخیره مکان منتخب");
    }
  };

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation();
    const res = await api.delete(`/api/v1/locations/favorites/${id}`);
    setDeletingId(null);
    if (res.success) {
      toast.success("مکان منتخب حذف شد");
      await queryClient.invalidateQueries({ queryKey: ["location-favorites"] });
    } else {
      toast.error(res.error || "خطا در حذف مکان منتخب");
    }
  };

  const filteredFavorites = favorites.filter((f) =>
    mode === "origin" ? f.is_origin : f.is_destination
  );

  return (
    <div className="mb-5">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-300">
          <BookmarkIcon className="h-4 w-4 text-amber-400" />
          <span>مکان‌های محبوب و پرکاربرد ({filteredFavorites.length})</span>
        </div>
        <button
          type="button"
          onClick={() => setShowSaveModal(!showSaveModal)}
          className="text-[11px] text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1"
        >
          <PlusIcon className="h-3.5 w-3.5" />
          <span>ذخیره مکان فعلی</span>
        </button>
      </div>

      {isLoading && <p className="text-[11px] text-slate-500">در حال بارگذاری مکان‌های منتخب...</p>}
      {isError && (
        <button type="button" onClick={() => void refetch()} className="text-[11px] font-bold text-amber-400 hover:text-amber-300">
          دریافت مکان‌های منتخب ناموفق بود؛ تلاش مجدد
        </button>
      )}

      {showSaveModal && (
        <div className="p-3 mb-3 rounded-xl bg-slate-900 border border-cyan-500/30 space-y-2">
          <label className="block text-xs text-slate-300 font-semibold">عنوان مکان جدید:</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="مثال: انبار مرکزی یا کارخانه A"
              className="field flex-1 text-xs"
            />
            <button
              type="button"
              onClick={handleSaveCurrent}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs shrink-0 flex items-center gap-1"
            >
              <CheckIcon className="h-3.5 w-3.5" />
              <span>ذخیره</span>
            </button>
          </div>
        </div>
      )}

      {filteredFavorites.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {filteredFavorites.map((fav) => (
            <div
              key={fav.id}
              onClick={() => onSelectFavorite(fav)}
              onKeyDown={(e) => {
                if ((e.key === "Enter" || e.key === " ") && deletingId !== fav.id) {
                  e.preventDefault();
                  onSelectFavorite(fav);
                }
              }}
              role="button"
              tabIndex={0}
              aria-label={`انتخاب مکان ${fav.title} در ${fav.city}`}
              className="group relative cursor-pointer px-3 py-2 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-white/5 hover:border-cyan-500/40 text-xs font-medium text-slate-200 transition-all flex items-center gap-2"
            >
              <span>{fav.title}</span>
              <span className="text-[10px] text-slate-400 font-normal">({fav.city})</span>

              {deletingId === fav.id ? (
                <div className="flex items-center gap-1 me-1" onClick={(e) => e.stopPropagation()}>
                  <button
                    type="button"
                    onClick={(e) => handleDelete(fav.id, e)}
                    className="text-[10px] font-bold text-rose-400 hover:underline"
                  >
                    تأیید
                  </button>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeletingId(null);
                    }}
                    className="text-[10px] text-slate-400 hover:underline"
                  >
                    لغو
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeletingId(fav.id);
                  }}
                  aria-label={`حذف مکان ${fav.title}`}
                  title="حذف مکان منتخب"
                  className="opacity-0 group-hover:opacity-100 text-rose-400 hover:text-rose-300 transition-opacity p-0.5"
                >
                  <TrashIcon className="h-3 w-3" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
});
