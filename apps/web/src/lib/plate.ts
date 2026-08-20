const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
export const PERSIAN_PLATE_LETTERS = "اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی";

/**
 * حروف ویژه و پرکاربرد پلاک در ناوگان ترابری و عمومی
 */
export const POPULAR_PLATE_LETTERS = [
  { letter: "ع", label: "ع (عمومی / باری)", isTruck: true },
  { letter: "ت", label: "ت (تاکسی / ترانزیت)", isTruck: false },
  { letter: "الف", label: "الف (دولتی)", isTruck: false },
  { letter: "ک", label: "ک (کشاورزی / ادوات)", isTruck: true },
] as const;

/**
 * تمامی حروف مجاز پلاک ملی ایران
 */
export const ALL_PLATE_LETTERS = [
  "ع", "ت", "الف", "ب", "ج", "د", "س", "ص", "ط", "ق", "ل", "م", "ن", "و", "ه", "ی", "پ", "ث", "ز", "ش", "ک",
] as const;

/**
 * نگاشت کلیدهای استاندارد کیبورد انگلیسی به حروف پلاک فارسی در صورت اشتباه بودن زبان ورودی
 */
const EN_TO_FA_KEY_MAP: Record<string, string> = {
  q: "ض", w: "ص", e: "ث", r: "ق", t: "ف", y: "غ", u: "ع", i: "ه", o: "خ", p: "ح",
  a: "ش", s: "س", d: "ی", f: "ب", g: "ل", h: "ا", j: "ت", k: "ن", l: "م",
  z: "ظ", x: "ط", c: "ز", v: "ر", b: "ذ", n: "د", m: "پ",
};

export function mapEnglishKeyToPersianLetter(char: string): string {
  const lower = char.toLowerCase();
  return EN_TO_FA_KEY_MAP[lower] || char;
}

export function normalizeDigits(value: string): string {
  let normalized = value;

  for (const [index, digit] of Array.from(PERSIAN_DIGITS).entries()) {
    normalized = normalized.replaceAll(digit, String(index));
  }

  for (const [index, digit] of Array.from(ARABIC_DIGITS).entries()) {
    normalized = normalized.replaceAll(digit, String(index));
  }

  return normalized;
}

export function normalizePersianText(value: string): string {
  return value
    .replaceAll("ي", "ی")
    .replaceAll("ك", "ک")
    .replaceAll("أ", "ا")
    .replaceAll("إ", "ا")
    .replaceAll("ة", "ه")
    .replaceAll("‌", "") // حذف نیم‌فاصله
    .trim();
}

export interface PlateParts {
  part1: string; // ۲ رقم اول (سمت چپ)
  part2: string; // حرف میانی
  part3: string; // ۳ رقم وسط
  part4: string; // ۲ رقم کد ایران (سمت راست)
}

/**
 * تحلیل هوشمند هرگونه رشته ورودی پلاک و تفکیک آن به ۴ بخش استاندارد
 */
export function parsePlateString(val: string): PlateParts {
  if (!val) return { part1: "", part2: "", part3: "", part4: "" };
  
  // اگر مقدار صرفاً کلمه "ایران" بود (باگ قبلی)، خالی برگردان
  if (val.trim() === "ایران") return { part1: "", part2: "", part3: "", part4: "" };

  const normalized = normalizeDigits(normalizePersianText(val))
    .replace(/[\s\-_/\\.|,]+/g, "")
    .replaceAll("ايران", "ایران");

  // حالت ۱: فرمت کامل استاندارد مثل 12ع345ایران67 یا 12الف34567
  const fullMatch = normalized.match(/^(\d{2})(الف|[^\d]+)(\d{3})(?:ایران)?(\d{2})$/u);
  if (fullMatch) {
    return {
      part1: fullMatch[1],
      part2: fullMatch[2].replaceAll("ایران", "").trim(),
      part3: fullMatch[3],
      part4: fullMatch[4],
    };
  }

  // حالت ۲: فرمت معکوس متنی رایج در برخی پیامک‌ها: ایران67-345ع12 یا 67-345ع12
  const reverseMatch = normalized.match(/^(?:ایران)?(\d{2})(\d{3})(الف|[^\d]+)(\d{2})$/u);
  if (reverseMatch) {
    return {
      part1: reverseMatch[4],
      part2: reverseMatch[3].replaceAll("ایران", "").trim(),
      part3: reverseMatch[2],
      part4: reverseMatch[1],
    };
  }

  // حالت ۳: تطابق تدریجی و جزئی هنگام تایپ
  const partial = normalized.replaceAll("ایران", "");
  const partialMatch = partial.match(/^(\d{0,2})(الف|[^\d]*)(\d{0,3})(\d{0,2})$/u);
  if (partialMatch) {
    return {
      part1: partialMatch[1] || "",
      part2: (partialMatch[2] || "").trim(),
      part3: partialMatch[3] || "",
      part4: partialMatch[4] || "",
    };
  }

  return { part1: "", part2: "", part3: "", part4: "" };
}

export function formatPlatePartsToString(parts: PlateParts): string {
  const { part1, part2, part3, part4 } = parts;
  if (!part1 && !part2 && !part3 && !part4) {
    return "";
  }
  // اگر پلاک کامل باشد:
  if (part1 && part2 && part3 && part4) {
    return `${part1}${part2}${part3}ایران${part4}`;
  }
  // اگر ناقص باشد، مقدار بدون "ایران" اضافه بازگردانده می‌شود تا فرم دچار خطای کاذب نشود
  return `${part1}${part2}${part3}${part4 ? `ایران${part4}` : ""}`;
}

export function canonicalizePlate(value: string): string {
  if (!value || value.trim() === "" || value.trim() === "ایران") return "";
  
  const parsed = parsePlateString(value);
  if (parsed.part1 && parsed.part2 && parsed.part3 && parsed.part4) {
    return `${parsed.part1}${parsed.part2}${parsed.part3}ایران${parsed.part4}`;
  }

  const normalized = normalizeDigits(normalizePersianText(value)).replace(/\s+/g, "").replace(/-/g, "").replaceAll("ايران", "ایران");
  return normalized === "ایران" ? "" : normalized;
}

export function isValidIranPlate(value: string): boolean {
  if (!value) return false;
  const canonical = canonicalizePlate(value);
  return new RegExp(`^\\d{2}(الف|[${PERSIAN_PLATE_LETTERS}])\\d{3}ایران\\d{2}$`, "u").test(canonical);
}

