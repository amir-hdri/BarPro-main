'use client';

import { useEffect, useState } from 'react';
import { MapPinIcon, RouteIcon } from 'lucide-react';

import { api } from '@/lib/api';
import type { DistanceResponse } from '@/lib/types';

interface RouteDistanceBadgeProps {
  originCoords: { lat: number; lng: number } | null;
  destinationCoords: { lat: number; lng: number } | null;
}

/**
 * نمایش زندهٔ فاصله و زمان تخمینی بین مبدأ و مقصد با استفاده از
 * `POST /api/v1/locations/distance` (Neshan + fallback هاورساین).
 * تنها زمانی محاسبه می‌شود که مختصات هر دو طرف مشخص باشد.
 */
export function RouteDistanceBadge({ originCoords, destinationCoords }: RouteDistanceBadgeProps) {
  const [distance, setDistance] = useState<DistanceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!originCoords || !destinationCoords) {
      setDistance(null);
      setError(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    api
      .post<DistanceResponse>(
        '/api/v1/locations/distance',
        {
          origin_lat: originCoords.lat,
          origin_lng: originCoords.lng,
          dest_lat: destinationCoords.lat,
          dest_lng: destinationCoords.lng,
        },
        { signal: controller.signal }
      )
      .then((res) => {
        if (res.success && res.data) {
          setDistance(res.data);
        } else {
          setError(res.error || 'محاسبهٔ فاصله ممکن نشد');
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setError('خطا در محاسبهٔ فاصله');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [originCoords, destinationCoords]);

  if (!originCoords || !destinationCoords) {
    return null;
  }

  return (
    <div className="mt-4 flex items-center gap-3 rounded-2xl bg-cyan-500/5 border border-cyan-500/20 px-4 py-3 backdrop-blur-sm">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/20">
        <RouteIcon className="h-4 w-4 text-cyan-400" />
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
          <span className="h-2 w-2 animate-ping rounded-full bg-cyan-400" />
          در حال محاسبهٔ فاصله و زمان مسیر…
        </div>
      )}

      {!loading && error && (
        <div className="flex items-center gap-2 text-xs font-bold text-amber-400">
          <MapPinIcon className="h-4 w-4" />
          {error}
        </div>
      )}

      {!loading && !error && distance && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
          <span className="font-black text-cyan-300">{distance.distance_text}</span>
          <span className="font-bold text-slate-300">⏱ {distance.duration_text}</span>
          <span className="rounded-lg bg-white/5 border border-white/10 px-2 py-0.5 text-[10px] font-bold text-slate-400">
            {distance.source === 'neshan' ? 'Neshan' : 'تخمین محلی'}
          </span>
        </div>
      )}
    </div>
  );
}
