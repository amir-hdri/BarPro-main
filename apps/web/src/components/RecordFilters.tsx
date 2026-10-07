'use client';

import { useId } from 'react';
import type { Driver } from '@/lib/types';
import { EMPTY_RECORD_FILTERS, tehranDateKey, type RecordFilters as Filters } from '@/lib/record-filters';

const waybillStatuses = [
  ['registered', 'ثبت‌شده'], ['pending', 'در انتظار'], ['queued', 'در صف'],
  ['in_progress', 'در حال اجرا'], ['waiting_auth', 'در انتظار ورود'],
  ['otp_backoff', 'در انتظار پیامک'], ['unknown', 'نتیجه نامشخص'],
  ['reconciling', 'در حال تطبیق'], ['success', 'موفق'], ['failed', 'ناموفق'],
  ['needs_review', 'نیازمند بررسی'],
];
const fuelStatuses = [
  ['pending', 'در صف'], ['processing', 'در حال اجرا'], ['success', 'موفق'],
  ['failed', 'ناموفق'], ['stale', 'منقضی‌شده'],
];

export function RecordFilters({ value, onChange, drivers, driversError, category }: {
  value: Filters;
  onChange: (next: Filters) => void;
  drivers: Driver[];
  driversError?: string | null;
  category: 'waybills' | 'fuel';
}) {
  const id = useId();
  const update = (patch: Partial<Filters>) => onChange({ ...value, ...patch });
  const selected = drivers.some(driver => String(driver.id) === value.driverId);
  return (
    <section aria-label="فیلتر رکوردها" className="rounded-2xl border border-white/10 bg-slate-900/50 p-4 sm:p-5 text-white">
      <h2 className="text-sm font-bold">انتخاب راننده و روز</h2>
      <p className="mt-1 text-xs leading-6 text-slate-400">زمان ثبت درخواست‌ها به وقت تهران است. هر استعلام یا بارنامه جداگانه نمایش داده می‌شود.</p>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-driver`} className="mb-2 block text-xs font-bold text-slate-300">راننده</label>
          <select id={`${id}-driver`} className="field touch-target" value={value.driverId} onChange={event => update({ driverId: event.target.value })}>
            <option value="">همه رانندگان</option>
            {value.driverId && !selected && <option value={value.driverId}>راننده با شناسه {value.driverId}</option>}
            {drivers.map(driver => <option key={driver.id} value={driver.id}>{driver.full_name} — {driver.driver_national_code}</option>)}
          </select>
          {driversError && <p role="alert" className="mt-2 text-xs text-rose-300">{driversError}</p>}
        </div>
        <div>
          <label htmlFor={`${id}-day`} className="mb-2 block text-xs font-bold text-slate-300">روز ثبت درخواست (تقویم میلادی)</label>
          <div className="flex gap-2">
            <input id={`${id}-day`} type="date" className="field min-w-0 flex-1 touch-target" value={value.day} onChange={event => update({ day: event.target.value, dateFrom: '', dateTo: '' })} />
            <button type="button" className="touch-target rounded-xl border border-cyan-500/30 px-4 text-xs font-bold text-cyan-300" onClick={() => update({ day: tehranDateKey(), dateFrom: '', dateTo: '' })}>امروز</button>
          </div>
        </div>
      </div>
      <details className="mt-4 border-t border-white/10 pt-2">
        <summary className="touch-target flex cursor-pointer items-center text-xs font-bold text-slate-300">فیلترهای بیشتر: بازه تاریخ، وضعیت و پلاک</summary>
        <div className="mt-2 grid gap-4 sm:grid-cols-2">
          <div><label htmlFor={`${id}-from`} className="mb-2 block text-xs text-slate-300">از تاریخ (میلادی)</label><input id={`${id}-from`} type="date" value={value.dateFrom} className="field touch-target" onChange={event => update({ dateFrom: event.target.value, day: '' })} /></div>
          <div><label htmlFor={`${id}-to`} className="mb-2 block text-xs text-slate-300">تا تاریخ (میلادی، شامل این روز)</label><input id={`${id}-to`} type="date" min={value.dateFrom || undefined} value={value.dateTo} className="field touch-target" onChange={event => update({ dateTo: event.target.value, day: '' })} /></div>
          <div><label htmlFor={`${id}-status`} className="mb-2 block text-xs text-slate-300">وضعیت</label><select id={`${id}-status`} value={value.status} className="field touch-target" onChange={event => update({ status: event.target.value })}><option value="">همه وضعیت‌ها</option>{(category === 'fuel' ? fuelStatuses : waybillStatuses).map(([status, label]) => <option key={status} value={status}>{label}</option>)}</select></div>
          <div><label htmlFor={`${id}-plate`} className="mb-2 block text-xs text-slate-300">پلاک خودرو</label><input id={`${id}-plate`} value={value.plate} className="field touch-target" placeholder="مثلاً ۱۲ع۳۴۵" onChange={event => update({ plate: event.target.value })} /></div>
        </div>
      </details>
      {Object.values(value).some(Boolean) && <button type="button" className="mt-2 touch-target rounded-xl border border-white/10 px-4 text-xs text-slate-300" onClick={() => onChange({ ...EMPTY_RECORD_FILTERS })}>نمایش همه رکوردها</button>}
    </section>
  );
}
