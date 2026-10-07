import test from 'node:test';
import assert from 'node:assert/strict';
import { nextUnobservedInquiry } from '../src/lib/fuel-polling.ts';

test('a timed-out inquiry is not restarted when its pending record refreshes', () => {
  const observed = new Set();
  const pending = [{ id: 7, status: 'pending' }];
  const first = nextUnobservedInquiry(pending, observed, null);
  assert.equal(first.id, 7);
  observed.add(first.id);
  assert.equal(nextUnobservedInquiry([{ id: 7, status: 'processing' }], observed, null), undefined);
  assert.equal(nextUnobservedInquiry([...pending, { id: 8, status: 'pending' }], observed, null).id, 8);
});

test('automatic observation neither interrupts another inquiry nor restarts a terminal one', () => {
  assert.equal(nextUnobservedInquiry([{ id: 2, status: 'pending' }], new Set(), 1), undefined);
  assert.equal(nextUnobservedInquiry([{ id: 3, status: 'success' }, { id: 4, status: 'failed' }], new Set(), null), undefined);
});
