import test from 'node:test';
import assert from 'node:assert/strict';

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const PERSIAN_PLATE_LETTERS = "اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی";

function normalizeDigits(value) {
  let normalized = value;
  for (const [index, digit] of Array.from(PERSIAN_DIGITS).entries()) {
    normalized = normalized.replaceAll(digit, String(index));
  }
  for (const [index, digit] of Array.from(ARABIC_DIGITS).entries()) {
    normalized = normalized.replaceAll(digit, String(index));
  }
  return normalized;
}

function normalizePersianText(value) {
  return value.replaceAll("ي", "ی").replaceAll("ك", "ک").replaceAll("أ", "ا").replaceAll("إ", "ا").replaceAll("ة", "ه");
}

function canonicalizePlate(value) {
  const normalized = normalizeDigits(normalizePersianText(value)).replace(/\s+/g, "").replace(/-/g, "").replaceAll("ايران", "ایران");
  const compact = normalized.replaceAll("ایران", "");
  const fullMatch = compact.match(new RegExp(`^(\\d{2})(الف|[${PERSIAN_PLATE_LETTERS}])(\\d{3})(\\d{2})$`, "u"));

  if (fullMatch) {
    return `${fullMatch[1]}${fullMatch[2]}${fullMatch[3]}ایران${fullMatch[4]}`;
  }
  return normalized;
}

function isValidIranPlate(value) {
  const canonical = canonicalizePlate(value);
  return new RegExp(`^\\d{2}(الف|[${PERSIAN_PLATE_LETTERS}])\\d{3}ایران\\d{2}$`, "u").test(canonical);
}

test('plate canonicalization with persian digits', () => {
  assert.equal(canonicalizePlate('۱۲ب۳۴۵ایران۶۷'), '12ب345ایران67');
  assert.equal(canonicalizePlate('12 ب 345 - 67'), '12ب345ایران67');
  assert.equal(isValidIranPlate('۱۲ب۳۴۵ایران۶۷'), true);
  assert.equal(isValidIranPlate('12ب345ایران67'), true);
  assert.equal(isValidIranPlate('invalid-plate'), false);
});

test('digits normalization', () => {
  assert.equal(normalizeDigits('۰۱۲۳۴۵۶۷۸۹'), '0123456789');
  assert.equal(normalizeDigits('٠١٢٣٤٥٦٧٨٩'), '0123456789');
});
