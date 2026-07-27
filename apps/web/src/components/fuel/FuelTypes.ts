export interface Driver {
  id: number;
  full_name: string;
  driver_national_code: string;
  utcms_username: string;
  status: string;
}

export interface FuelInquiry {
  id: number;
  client_id: number;
  driver_id: number | null;
  driver_name: string | null;
  national_code: string;
  vin: string | null;
  barname_count: number | null;
  total_tonnage: number | null;
  total_distance: number | null;
  fuel_consumed_liters: number | null;
  calculated_quota_liters: number | null;
  year: number;
  month: number;
  status: string;
  retry_count: number;
  error_message: string | null;
  result_json: Record<string, unknown> | null;
  captcha_solved: boolean;
  solving_time_seconds: number | null;
  ocr_provider_used: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export const PERSIAN_MONTHS: Record<number, string> = {
  1: 'فروردین',
  2: 'اردیبهشت',
  3: 'خرداد',
  4: 'تیر',
  5: 'مرداد',
  6: 'شهریور',
  7: 'مهر',
  8: 'آبان',
  9: 'آذر',
  10: 'دی',
  11: 'بهمن',
  12: 'اسفند',
};

export const toPersianDigitsPreserveZero = (str: string | number): string => {
  if (str === undefined || str === null) return '';
  const map: Record<string, string> = {
    '0': '۰', '1': '۱', '2': '۲', '3': '۳', '4': '۴',
    '5': '۵', '6': '۶', '7': '۷', '8': '۸', '9': '۹'
  };
  return str.toString().replace(/[0-9]/g, (w) => map[w] || w);
};

export const getTrackingCode = (inquiry: FuelInquiry): string => {
  const yy = inquiry.year ? inquiry.year.toString().slice(-2) : '00';
  const mm = inquiry.month ? inquiry.month.toString().padStart(2, '0') : '00';
  const idStr = inquiry.id.toString().padStart(4, '0');
  return toPersianDigitsPreserveZero(`UTC-${yy}${mm}-${idStr}`);
};
