import type { Driver, FuelInquiry } from "@/lib/types";

export type { Driver, FuelInquiry };

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

export const getTrackingCode = (inquiry: { id: number; year?: number | null; month?: number | null }): string => {
  const yy = inquiry.year ? inquiry.year.toString().slice(-2) : '00';
  const mm = inquiry.month ? inquiry.month.toString().padStart(2, '0') : '00';
  const idStr = inquiry.id.toString().padStart(4, '0');
  return toPersianDigitsPreserveZero(`UTC-${yy}${mm}-${idStr}`);
};

export const FUEL_INQUIRY_ERROR_DESCRIPTIONS: Record<string, string> = {
  "101": "اطلاعات ورودی (کد ملی یا پلاک) در سامانه یافت نشد",
  "102": "عدم موفقیت در احراز هویت یا ورود به سامانه سوخت",
  "103": "سامانه سوخت پاسخگو نبود (تایم‌اوت ارتباط)",
  "104": "خطا در حل کپچای امنیتی سامانه سوخت",
  "105": "تغییر ساختار سامانه سوخت و عدم دسترسی به داده‌ها",
  "106": "شناسایی و مسدودسازی توسط دیوار امنیتی سامانه",
  "107": "خطای موقت شبکه و زیرساخت ارتباطی",
  "108": "محدودیت منابع یا خطای داخلی مرورگر در ورکر",
};

export function formatFuelErrorMessage(errorCode?: string | null): string {
  if (!errorCode) return "استعلام با خطا مواجه شد";
  const desc = FUEL_INQUIRY_ERROR_DESCRIPTIONS[errorCode.trim()];
  return desc ? `${desc} (${errorCode})` : errorCode;
}
