import test from 'node:test';
import assert from 'node:assert/strict';
import {
  gregorianToJalali,
  jalaliToGregorian,
  isJalaliLeapYear,
  getJalaliMonthDays,
  gregorianIsoToJalali,
  jalaliToGregorianIso,
  formatJalaliDisplay,
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
  assert.equal(formatJalaliDate('2026-10-11'), '۱۴۰۵/۰۷/۱۹');
  assert.equal(formatJalaliDisplay(''), '-');
  assert.equal(formatJalaliDate(null), '-');
});
