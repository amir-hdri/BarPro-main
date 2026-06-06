const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const PERSIAN_PLATE_LETTERS = "اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی";

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
  return value.replaceAll("ي", "ی").replaceAll("ك", "ک").replaceAll("أ", "ا").replaceAll("إ", "ا").replaceAll("ة", "ه");
}

export function canonicalizePlate(value: string): string {
  const normalized = normalizeDigits(normalizePersianText(value)).replace(/\s+/g, "").replace(/-/g, "").replaceAll("ايران", "ایران");
  const compact = normalized.replaceAll("ایران", "");
  const fullMatch = compact.match(new RegExp(`^(\\d{2})(الف|[${PERSIAN_PLATE_LETTERS}])(\\d{3})(\\d{2})$`, "u"));

  if (fullMatch) {
    return `${fullMatch[1]}${fullMatch[2]}${fullMatch[3]}ایران${fullMatch[4]}`;
  }

  return normalized;
}

export function isValidIranPlate(value: string): boolean {
  const canonical = canonicalizePlate(value);
  return new RegExp(`^\\d{2}(الف|[${PERSIAN_PLATE_LETTERS}])\\d{3}ایران\\d{2}$`, "u").test(canonical);
}
