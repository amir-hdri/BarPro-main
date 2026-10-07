import { canonicalizePlate } from './plate';

export interface RecordFilters {
  driverId: string;
  day: string;
  dateFrom: string;
  dateTo: string;
  status: string;
  plate: string;
}

export const EMPTY_RECORD_FILTERS: RecordFilters = {
  driverId: '', day: '', dateFrom: '', dateTo: '', status: '', plate: '',
};

/** API timestamps without an offset are UTC, never the browser's timezone. */
export function parseApiDate(value: string): Date {
  return new Date(/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`);
}

/** Gregorian API date for a Tehran calendar day, regardless of browser timezone. */
export function tehranDateKey(value: Date | string = new Date()): string {
  const date = typeof value === 'string' ? parseApiDate(value) : value;
  if (!Number.isFinite(date.getTime())) return '';
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(date);
}

export function recordFilterParams(filters: RecordFilters): Record<string, string> {
  const params: Record<string, string> = {};
  if (/^[1-9]\d*$/.test(filters.driverId)) params.driver_id = filters.driverId;
  if (filters.status) params.status = filters.status;
  const plate = canonicalizePlate(filters.plate);
  if (plate) params.plate_number = plate;
  if (filters.day || filters.dateFrom) params.date_from = filters.day || filters.dateFrom;
  if (filters.day || filters.dateTo) params.date_to = filters.day || filters.dateTo;
  return params;
}

export function recordFiltersFromSearch(search: string): RecordFilters {
  const params = new URLSearchParams(search);
  const driverId = params.get('driver_id') || '';
  const day = params.get('day') || '';
  return {
    ...EMPTY_RECORD_FILTERS,
    driverId: /^[1-9]\d*$/.test(driverId) ? driverId : '',
    day: /^\d{4}-\d{2}-\d{2}$/.test(day) ? day : '',
  };
}
