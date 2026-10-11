import test from 'node:test';
import assert from 'node:assert/strict';
import {
  gregorianToJalali,
  jalaliToGregorian,
  isJalaliLeapYear,
  getJalaliMonthDays,
  getJalaliFirstDayOfWeek,
  gregorianIsoToJalali,
  jalaliToGregorianIso,
  formatJalaliDisplay,
  toPersianDigits,
  toEnglishDigits,
} from '../src/lib/jalali.ts';
import { formatJalaliDate } from '../src/lib/format.ts';

test('gregorianToJalali and jalaliToGregorian exact bidirectional conversion', () => {
  // Known reference points:
  // Nowruz 1405: 2026-03-21
  assert.deepEqual(gregorianToJalali(2026, 3, 21), [1405, 1, 1]);
  assert.deepEqual(jalaliToGregorian(1405, 1, 1), [2026, 3, 21]);

  // Mehr 1405: 2026-10-11 -> 1405-07-19
  assert.deepEqual(gregorianToJalali(2026, 10, 11), [1405, 7, 19]);
  assert.deepEqual(jalaliToGregorian(1405, 7, 19), [2026, 10, 11]);

  // Roundtrip for various dates
  for (const [gy, gm, gd] of [[2024, 1, 1], [2025, 6, 15], [2026, 10, 11], [2027, 12, 31]]) {
    const [jy, jm, jd] = gregorianToJalali(gy, gm, gd);
    assert.deepEqual(jalaliToGregorian(jy, jm, jd), [gy, gm, gd]);
  }
});

test('leap year and month days', () => {
  assert.equal(isJalaliLeapYear(1403), true);
  assert.equal(isJalaliLeapYear(1404), false);
  assert.equal(isJalaliLeapYear(1405), false);
  assert.equal(isJalaliLeapYear(1408), true);

  assert.equal(getJalaliMonthDays(1405, 1), 31);
  assert.equal(getJalaliMonthDays(1405, 7), 30);
  assert.equal(getJalaliMonthDays(1405, 12), 29);
  assert.equal(getJalaliMonthDays(1403, 12), 30); // Leap year Esfand
});

test('ISO string conversions and formatting', () => {
  assert.deepEqual(gregorianIsoToJalali('2026-10-11'), { jy: 1405, jm: 7, jd: 19 });
  assert.equal(jalaliToGregorianIso(1405, 7, 19), '2026-10-11');
  assert.equal(formatJalaliDisplay('2026-10-11'), '۱۴۰۵/۰۷/۱۹');
  assert.equal(formatJalaliDisplay('2026-10-11', false), '1405/07/19');
  assert.equal(formatJalaliDate('2026-10-11'), '۱۴۰۵/۰۷/۱۹');
  assert.equal(formatJalaliDisplay(''), '-');
  assert.equal(formatJalaliDate(null), '-');
  assert.equal(gregorianIsoToJalali(''), null);
  assert.equal(gregorianIsoToJalali('not-a-date'), null);
  assert.equal(gregorianIsoToJalali('2026-00-11'), null);
});

test('Persian and English digit conversions', () => {
  assert.equal(toPersianDigits('1405/07/19'), '۱۴۰۵/۰۷/۱۹');
  assert.equal(toPersianDigits(12345), '۱۲۳۴۵');
  assert.equal(toEnglishDigits('۱۴۰۵/۰۷/۱۹'), '1405/07/19');
  assert.equal(toEnglishDigits('۱۲۳۴۵۶۷۸۹۰'), '1234567890');
});

test('weekday and month boundary edge cases', () => {
  // 1405-01-01 (2026-03-21) is Saturday (شنبه = 0)
  assert.equal(getJalaliFirstDayOfWeek(1405, 1), 0);
  // 1405-07-01 (2026-09-23) is Wednesday (چهارشنبه = 4)
  assert.equal(getJalaliFirstDayOfWeek(1405, 7), 4);

  // Leap year Esfand 30 bidirectional roundtrip (1403-12-30 -> 2025-03-20)
  const [gy, gm, gd] = jalaliToGregorian(1403, 12, 30);
  assert.deepEqual([gy, gm, gd], [2025, 3, 20]);
  assert.deepEqual(gregorianToJalali(gy, gm, gd), [1403, 12, 30]);

  // Non-leap year Esfand 29 bidirectional roundtrip (1404-12-29 -> 2026-03-20)
  const [gy2, gm2, gd2] = jalaliToGregorian(1404, 12, 29);
  assert.deepEqual([gy2, gm2, gd2], [2026, 3, 20]);
  assert.deepEqual(gregorianToJalali(gy2, gm2, gd2), [1404, 12, 29]);
});
