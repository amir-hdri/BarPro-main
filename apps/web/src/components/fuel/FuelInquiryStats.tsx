'use client';

import React, { memo } from 'react';
import {
  FireIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { toPersianDigitsPreserveZero } from './FuelTypes';

interface FuelInquiryStatsProps {
  stats: {
    total: number;
    completed: number;
    pending: number;
    failed: number;
    totalFuel: number;
  };
}

export const FuelInquiryStats = memo(function FuelInquiryStats({ stats }: FuelInquiryStatsProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 sm:gap-4 mb-6">
      <div className="p-3 sm:p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl">
        <div className="flex items-center gap-2.5 text-slate-400 mb-1.5">
          <FireIcon className="w-4 sm:w-5 h-4 sm:h-5 text-amber-400 shrink-0" />
          <span className="text-xs sm:text-sm font-medium">کل استعلام‌ها</span>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-slate-100">
          {toPersianDigitsPreserveZero(stats.total)}
        </div>
      </div>

      <div className="p-3 sm:p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl">
        <div className="flex items-center gap-2.5 text-slate-400 mb-1.5">
          <CheckCircleIcon className="w-4 sm:w-5 h-4 sm:h-5 text-emerald-400 shrink-0" />
          <span className="text-xs sm:text-sm font-medium">تکمیل‌شده</span>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-emerald-400">
          {toPersianDigitsPreserveZero(stats.completed)}
        </div>
      </div>

      <div className="p-3 sm:p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl">
        <div className="flex items-center gap-2.5 text-slate-400 mb-1.5">
          <ClockIcon className="w-4 sm:w-5 h-4 sm:h-5 text-blue-400 shrink-0" />
          <span className="text-xs sm:text-sm font-medium">در حال پردازش</span>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-blue-400">
          {toPersianDigitsPreserveZero(stats.pending)}
        </div>
      </div>

      <div className="p-3 sm:p-4 rounded-xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl">
        <div className="flex items-center gap-2.5 text-slate-400 mb-1.5">
          <ExclamationTriangleIcon className="w-4 sm:w-5 h-4 sm:h-5 text-rose-400 shrink-0" />
          <span className="text-xs sm:text-sm font-medium">ناموفق</span>
        </div>
        <div className="text-xl sm:text-2xl font-bold text-rose-400">
          {toPersianDigitsPreserveZero(stats.failed)}
        </div>
      </div>
    </div>
  );
});
