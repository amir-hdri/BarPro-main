'use client';

import { useState, useRef, useEffect, useId, useMemo } from 'react';
import {
  CalendarDaysIcon,
  ChevronRightIcon,
  ChevronLeftIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import {
  JALALI_MONTH_NAMES,
  JALALI_WEEKDAY_SHORT,
  gregorianIsoToJalali,
  jalaliToGregorianIso,
  getJalaliMonthDays,
  getJalaliFirstDayOfWeek,
  getTodayJalali,
  toPersianDigits,
  formatJalaliDisplay,
} from '@/lib/jalali';

export interface JalaliDatePickerProps {
  value?: string;
  onChange: (isoDate: string) => void;
  placeholder?: string;
  id?: string;
  className?: string;
  disabled?: boolean;
  required?: boolean;
  min?: string;
  max?: string;
  'aria-label'?: string;
}

export function JalaliDatePicker({
  value = '',
  onChange,
  placeholder = 'انتخاب تاریخ...',
  id: propId,
  className = '',
  disabled = false,
  required = false,
  'aria-label': ariaLabel,
}: JalaliDatePickerProps) {
  const generatedId = useId();
  const inputId = propId || generatedId;

  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const today = useMemo(() => getTodayJalali(), []);

  // Parse current value or fallback to today
  const selectedJalali = useMemo(() => {
    return gregorianIsoToJalali(value);
  }, [value]);

  // Calendar navigation state (viewed year and month)
  const [viewYear, setViewYear] = useState(() => selectedJalali?.jy ?? today.jy);
  const [viewMonth, setViewMonth] = useState(() => selectedJalali?.jm ?? today.jm);

  // Sync viewed month/year when selected value changes
  useEffect(() => {
    if (selectedJalali) {
      setViewYear(selectedJalali.jy);
      setViewMonth(selectedJalali.jm);
    }
  }, [selectedJalali]);

  // Close calendar on outside click
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen]);

  const monthDays = useMemo(() => {
    return getJalaliMonthDays(viewYear, viewMonth);
  }, [viewYear, viewMonth]);

  const firstDayOfWeek = useMemo(() => {
    return getJalaliFirstDayOfWeek(viewYear, viewMonth);
  }, [viewYear, viewMonth]);

  const handlePrevMonth = () => {
    if (viewMonth === 1) {
      setViewYear((y) => y - 1);
      setViewMonth(12);
    } else {
      setViewMonth((m) => m - 1);
    }
  };

  const handleNextMonth = () => {
    if (viewMonth === 12) {
      setViewYear((y) => y + 1);
      setViewMonth(1);
    } else {
      setViewMonth((m) => m + 1);
    }
  };

  const handleSelectDay = (day: number) => {
    const iso = jalaliToGregorianIso(viewYear, viewMonth, day);
    onChange(iso);
    setIsOpen(false);
  };

  const handleSelectToday = () => {
    const iso = jalaliToGregorianIso(today.jy, today.jm, today.jd);
    setViewYear(today.jy);
    setViewMonth(today.jm);
    onChange(iso);
    setIsOpen(false);
  };

  const handleClear = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange('');
  };

  // Year choices for quick selection
  const yearOptions = useMemo(() => {
    const start = today.jy - 5;
    const end = today.jy + 5;
    const years: number[] = [];
    for (let y = start; y <= end; y++) {
      years.push(y);
    }
    return years;
  }, [today.jy]);

  return (
    <div ref={containerRef} className="relative w-full">
      {/* Visual trigger input */}
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        aria-label={ariaLabel || 'انتخاب تاریخ خورشیدی'}
        onClick={() => !disabled && setIsOpen((prev) => !prev)}
        onKeyDown={(e) => {
          if (!disabled && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            setIsOpen((prev) => !prev);
          }
        }}
        className={`flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-slate-900/60 px-4 py-3.5 text-sm text-white transition hover:border-cyan-500/50 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 cursor-pointer ${
          disabled ? 'opacity-50 cursor-not-allowed' : ''
        } ${className}`}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <CalendarDaysIcon className="h-5 w-5 text-cyan-400 shrink-0" />
          <span className={`truncate font-medium ${value ? 'text-white' : 'text-slate-500'}`}>
            {value ? formatJalaliDisplay(value) : placeholder}
          </span>
        </div>

        {value && !disabled && (
          <button
            type="button"
            onClick={handleClear}
            className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
            aria-label="پاک کردن تاریخ"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Hidden real input for form integration / required validation */}
      <input
        type="hidden"
        id={inputId}
        value={value}
        required={required}
        readOnly
      />

      {/* Calendar dropdown popup */}
      {isOpen && (
        <div
          role="dialog"
          aria-label="تقویم شمسی"
          className="absolute z-50 mt-2 start-0 w-[300px] sm:w-[320px] rounded-2xl border border-white/15 bg-slate-950 p-4 shadow-2xl backdrop-blur-xl animate-in fade-in zoom-in-95 duration-150"
        >
          {/* Header: navigation & month/year selectors */}
          <div className="flex items-center justify-between gap-1 mb-4 pb-3 border-b border-white/10">
            <button
              type="button"
              onClick={handlePrevMonth}
              className="p-1.5 rounded-xl text-slate-300 hover:text-white hover:bg-white/10 transition"
              aria-label="ماه قبل"
            >
              <ChevronRightIcon className="h-5 w-5" />
            </button>

            <div className="flex items-center gap-1.5">
              <select
                value={viewMonth}
                onChange={(e) => setViewMonth(Number(e.target.value))}
                className="rounded-lg bg-slate-900 border border-white/10 px-2 py-1 text-xs font-bold text-white focus:outline-none focus:border-cyan-500 cursor-pointer"
              >
                {JALALI_MONTH_NAMES.map((m, idx) => (
                  <option key={m} value={idx + 1} className="bg-slate-900 text-white">
                    {m}
                  </option>
                ))}
              </select>

              <select
                value={viewYear}
                onChange={(e) => setViewYear(Number(e.target.value))}
                className="rounded-lg bg-slate-900 border border-white/10 px-2 py-1 text-xs font-bold text-white focus:outline-none focus:border-cyan-500 cursor-pointer"
              >
                {yearOptions.map((y) => (
                  <option key={y} value={y} className="bg-slate-900 text-white">
                    {toPersianDigits(y)}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={handleNextMonth}
              className="p-1.5 rounded-xl text-slate-300 hover:text-white hover:bg-white/10 transition"
              aria-label="ماه بعد"
            >
              <ChevronLeftIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Weekday headers */}
          <div className="grid grid-cols-7 gap-1 mb-2 text-center">
            {JALALI_WEEKDAY_SHORT.map((w, idx) => (
              <span
                key={w}
                className={`text-[11px] font-bold py-1 ${
                  idx === 6 ? 'text-rose-400' : 'text-slate-400'
                }`}
              >
                {w}
              </span>
            ))}
          </div>

          {/* Days grid */}
          <div className="grid grid-cols-7 gap-1 text-center">
            {Array.from({ length: firstDayOfWeek }).map((_, idx) => (
              <div key={`empty-${idx}`} className="h-9 w-9" />
            ))}

            {Array.from({ length: monthDays }).map((_, idx) => {
              const day = idx + 1;
              const isSelected =
                selectedJalali &&
                selectedJalali.jy === viewYear &&
                selectedJalali.jm === viewMonth &&
                selectedJalali.jd === day;
              const isToday =
                today.jy === viewYear && today.jm === viewMonth && today.jd === day;
              const isFriday = (firstDayOfWeek + idx) % 7 === 6;

              return (
                <button
                  key={day}
                  type="button"
                  onClick={() => handleSelectDay(day)}
                  className={`h-9 w-9 mx-auto rounded-xl text-xs font-bold flex items-center justify-center transition-all ${
                    isSelected
                      ? 'bg-cyan-500 text-slate-950 font-black shadow-lg shadow-cyan-500/30 scale-105'
                      : isToday
                      ? 'border border-cyan-400 text-cyan-300 hover:bg-cyan-500/20'
                      : isFriday
                      ? 'text-rose-400 hover:bg-white/10'
                      : 'text-slate-200 hover:bg-white/10'
                  }`}
                >
                  {toPersianDigits(day)}
                </button>
              );
            })}
          </div>

          {/* Footer actions */}
          <div className="mt-3 pt-3 border-t border-white/10 flex items-center justify-between">
            <button
              type="button"
              onClick={handleSelectToday}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-cyan-400 hover:bg-cyan-500/10 transition"
            >
              امروز ({toPersianDigits(today.jd)} {JALALI_MONTH_NAMES[today.jm - 1]})
            </button>

            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="px-3 py-1.5 rounded-lg text-xs font-bold text-slate-400 hover:text-white hover:bg-white/10 transition"
            >
              بستن
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
