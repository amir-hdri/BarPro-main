import test from 'node:test';
import assert from 'node:assert/strict';
import { requireShippingResult } from '../src/lib/shipping-result.ts';

test('rejected shipping requests preserve the API error and never acknowledge success', () => {
  for (const action of ['start', 'finish']) {
    assert.throws(() => requireShippingResult({ success: false, error: 'ثبت زنده GPS غیرفعال است' }, action), /ثبت زنده GPS غیرفعال است/);
  }
});

test('shipping requires the exact acknowledged operation, including on HTTP 200', () => {
  assert.doesNotThrow(() => requireShippingResult({ success: true, data: { status: 'started' } }, 'start'));
  assert.doesNotThrow(() => requireShippingResult({ success: true, data: { status: 'delivered' } }, 'finish'));
  for (const status of ['starting', 'finishing', 'unknown', 'accepted', 'ready']) {
    assert.throws(() => requireShippingResult({ success: true, data: { status } }, 'start'));
    assert.throws(() => requireShippingResult({ success: true, data: { status } }, 'finish'));
  }
  assert.throws(() => requireShippingResult({ success: true }, 'start'));
});
