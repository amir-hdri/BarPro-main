import test from 'node:test';
import assert from 'node:assert/strict';
import { EMPTY_RECORD_FILTERS, recordFilterParams, recordFiltersFromSearch, tehranDateKey } from '../src/lib/record-filters.ts';
import { formatDateTime } from '../src/lib/format.ts';

test('driver + day filter uses exact ID and both inclusive Tehran day boundaries', () => {
  assert.deepEqual(recordFilterParams({ ...EMPTY_RECORD_FILTERS, driverId: '42', day: '2026-10-06' }), {
    driver_id: '42', date_from: '2026-10-06', date_to: '2026-10-06',
  });
});

test('Tehran midnight crosses the UTC date and naive API timestamps are UTC', () => {
  assert.equal(tehranDateKey('2026-10-05T20:29:59Z'), '2026-10-05');
  assert.equal(tehranDateKey('2026-10-05T20:30:00Z'), '2026-10-06');
  assert.equal(tehranDateKey('2026-10-05T20:30:00'), '2026-10-06');
  assert.equal(tehranDateKey('2026-10-06T00:00:00+03:30'), '2026-10-06');
  assert.equal(formatDateTime('2026-10-05T20:30:00'), formatDateTime('2026-10-05T20:30:00Z'));
});

test('range and plate inputs retain canonical server contract', () => {
  assert.deepEqual(recordFilterParams({ ...EMPTY_RECORD_FILTERS, dateFrom: '2026-10-01', dateTo: '2026-10-06', plate: '۱۲ع۳۴۵ايران۶۷', status: 'success' }), {
    date_from: '2026-10-01', date_to: '2026-10-06', plate_number: '12ع345ایران67', status: 'success',
  });
});

test('driver links preserve the selected identity and date without accepting malformed IDs', () => {
  assert.deepEqual(recordFiltersFromSearch('?driver_id=42&day=2026-10-06&category=fuel'), { ...EMPTY_RECORD_FILTERS, driverId: '42', day: '2026-10-06' });
  assert.equal(recordFiltersFromSearch('?driver_id=42evil').driverId, '');
  assert.deepEqual(recordFilterParams(EMPTY_RECORD_FILTERS), {});
});
