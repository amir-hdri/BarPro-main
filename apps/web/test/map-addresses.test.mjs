import test from 'node:test';
import assert from 'node:assert/strict';
import { parseWaybillPayload } from '../src/lib/format.ts';

test('map receives full saved addresses rather than city labels', () => {
  const value = parseWaybillPayload({
    origin: 'تهران', destination: 'کرج',
    metadata_json: JSON.stringify({ origin: { address: 'خیابان نمونه، پلاک ۲' }, destination: { address: 'خیابان مقصد، پلاک ۳' } }),
  });
  assert.equal(value.originCity, 'تهران');
  assert.equal(value.originAddress, 'خیابان نمونه، پلاک ۲');
  assert.equal(value.destinationAddress, 'خیابان مقصد، پلاک ۳');
});

test('legacy addresses remain supported while object-valued addresses are rejected', () => {
  const value = parseWaybillPayload({ origin: { address: { invalid: true } }, origin_address: 'legacy origin', destination_address: 'legacy destination' });
  assert.equal(value.originAddress, 'legacy origin');
  assert.equal(value.destinationAddress, 'legacy destination');
  assert.equal(parseWaybillPayload(null).originAddress, null);
});
