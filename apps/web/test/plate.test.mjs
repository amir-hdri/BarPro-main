import test from 'node:test';
import assert from 'node:assert/strict';

const PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹";
const ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩";
const PERSIAN_PLATE_LETTERS = "اآبپتثجچحخدذرزژسشصضطظعغفقکگلمنوهی";

const EN_TO_FA_KEY_MAP = {
  q: "ض", w: "ص", e: "ث", r: "ق", t: "ف", y: "غ", u: "ع", i: "ه", o: "خ", p: "ح",
  a: "ش", s: "س", d: "ی", f: "ب", g: "ل", h: "ا", j: "ت", k: "ن", l: "م",
  z: "ظ", x: "ط", c: "ز", v: "ر", b: "ذ", n: "د", m: "پ",
};

function mapEnglishKeyToPersianLetter(char) {
  const lower = char.toLowerCase();
  return EN_TO_FA_KEY_MAP[lower] || char;
}

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
  return value
    .replaceAll("ي", "ی")
    .replaceAll("ك", "ک")
    .replaceAll("أ", "ا")
    .replaceAll("إ", "ا")
    .replaceAll("ة", "ه")
    .replaceAll("‌", "")
    .trim();
}

function parsePlateString(val) {
  if (!val) return { part1: "", part2: "", part3: "", part4: "" };
  if (val.trim() === "ایران") return { part1: "", part2: "", part3: "", part4: "" };

  const normalized = normalizeDigits(normalizePersianText(val))
    .replace(/[\s\-_/\\.|,]+/g, "")
    .replaceAll("ايران", "ایران");

  const fullMatch = normalized.match(/^(\d{2})(الف|[^\d]+)(\d{3})(?:ایران)?(\d{2})$/u);
  if (fullMatch) {
    return {
      part1: fullMatch[1],
      part2: fullMatch[2].replaceAll("ایران", "").trim(),
      part3: fullMatch[3],
      part4: fullMatch[4],
    };
  }

  const reverseMatch = normalized.match(/^(?:ایران)?(\d{2})(\d{3})(الف|[^\d]+)(\d{2})$/u);
  if (reverseMatch) {
    return {
      part1: reverseMatch[4],
      part2: reverseMatch[3].replaceAll("ایران", "").trim(),
      part3: reverseMatch[2],
      part4: reverseMatch[1],
    };
  }

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

function formatPlatePartsToString(parts) {
  const { part1, part2, part3, part4 } = parts;
  if (!part1 && !part2 && !part3 && !part4) {
    return "";
  }
  if (part1 && part2 && part3 && part4) {
    return `${part1}${part2}${part3}ایران${part4}`;
  }
  return `${part1}${part2}${part3}${part4 ? `ایران${part4}` : ""}`;
}

function canonicalizePlate(value) {
  if (!value || value.trim() === "" || value.trim() === "ایران") return "";
  const parsed = parsePlateString(value);
  if (parsed.part1 && parsed.part2 && parsed.part3 && parsed.part4) {
    return `${parsed.part1}${parsed.part2}${parsed.part3}ایران${parsed.part4}`;
  }
  const normalized = normalizeDigits(normalizePersianText(value)).replace(/\s+/g, "").replace(/-/g, "").replaceAll("ايران", "ایران");
  return normalized === "ایران" ? "" : normalized;
}

function isValidIranPlate(value) {
  if (!value) return false;
  const canonical = canonicalizePlate(value);
  return new RegExp(`^\\d{2}(الف|[${PERSIAN_PLATE_LETTERS}])\\d{3}ایران\\d{2}$`, "u").test(canonical);
}

test('plate canonicalization with persian digits', () => {
  assert.equal(canonicalizePlate('۱۲ب۳۴۵ایران۶۷'), '12ب345ایران67');
  assert.equal(canonicalizePlate('12 ب 345 - 67'), '12ب345ایران67');
  assert.equal(canonicalizePlate('۱۲ ع ۳۴۵ ایران ۶۷'), '12ع345ایران67');
  assert.equal(canonicalizePlate('12الف345ایران67'), '12الف345ایران67');
  assert.equal(isValidIranPlate('۱۲ب۳۴۵ایران۶۷'), true);
  assert.equal(isValidIranPlate('12ب345ایران67'), true);
  assert.equal(isValidIranPlate('12ع345ایران67'), true);
  assert.equal(isValidIranPlate('12الف345ایران67'), true);
  assert.equal(isValidIranPlate('invalid-plate'), false);
  assert.equal(isValidIranPlate(''), false);
  assert.equal(isValidIranPlate('ایران'), false);
});

test('digits normalization', () => {
  assert.equal(normalizeDigits('۰۱۲۳۴۵۶۷۸۹'), '0123456789');
  assert.equal(normalizeDigits('٠١٢٣٤٥٦٧٨٩'), '0123456789');
});

test('parsePlateString with various formats', () => {
  // Standard full
  assert.deepEqual(parsePlateString('12ع345ایران67'), { part1: '12', part2: 'ع', part3: '345', part4: '67' });
  // Reverse SMS copy: ایران 67 - 345 ع 12
  assert.deepEqual(parsePlateString('ایران67345ع12'), { part1: '12', part2: 'ع', part3: '345', part4: '67' });
  // With Alif (الف)
  assert.deepEqual(parsePlateString('12الف345ایران67'), { part1: '12', part2: 'الف', part3: '345', part4: '67' });
  // Partial / Empty
  assert.deepEqual(parsePlateString(''), { part1: '', part2: '', part3: '', part4: '' });
  assert.deepEqual(parsePlateString('ایران'), { part1: '', part2: '', part3: '', part4: '' });
});

test('formatPlatePartsToString and empty state handling', () => {
  assert.equal(formatPlatePartsToString({ part1: '', part2: '', part3: '', part4: '' }), '');
  assert.equal(formatPlatePartsToString({ part1: '12', part2: 'ع', part3: '345', part4: '67' }), '12ع345ایران67');
});

test('english keyboard key mapping to persian plate letters', () => {
  assert.equal(mapEnglishKeyToPersianLetter('u'), 'ع');
  assert.equal(mapEnglishKeyToPersianLetter('j'), 'ت');
  assert.equal(mapEnglishKeyToPersianLetter('f'), 'ب');
  assert.equal(mapEnglishKeyToPersianLetter('d'), 'ی');
});

