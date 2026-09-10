import test from 'node:test';
import assert from 'node:assert/strict';

import { confirmedTrackingCode, trackingAcknowledged } from '../src/lib/format.ts';

test('acknowledged dict result with tracking_received + code', () => {
  const ack = trackingAcknowledged({ tracking_code: 'UTC-123', confirmation_status: 'tracking_received' });
  assert.deepEqual(ack, { code: 'UTC-123' });
});

test('acknowledged JSON-string result', () => {
  const ack = trackingAcknowledged('{"tracking_code": "UTC-123", "confirmation_status": "tracking_received"}');
  assert.deepEqual(ack, { code: 'UTC-123' });
});

test('missing code is not acknowledged', () => {
  assert.equal(trackingAcknowledged({ confirmation_status: 'tracking_missing_history_required' }), null);
  assert.equal(trackingAcknowledged({ tracking_code: '   ', confirmation_status: 'tracking_received' }), null);
});

test('confirmed_by_history is not merely acknowledged', () => {
  assert.equal(
    trackingAcknowledged({ tracking_code: 'UTC-123', confirmation_status: 'confirmed_by_history' }),
    null,
  );
});

test('missing confirmation_status is not acknowledged', () => {
  assert.equal(trackingAcknowledged({ tracking_code: 'UTC-123' }), null);
  assert.equal(trackingAcknowledged(null), null);
});

test('confirmedTrackingCode stays strict (three witnesses)', () => {
  assert.equal(
    confirmedTrackingCode(
      { tracking_code: 'UTC-123', confirmation_status: 'tracking_received' },
      'unknown',
      null,
      null,
    ),
    null,
  );
  assert.equal(
    confirmedTrackingCode(
      { tracking_code: 'UTC-123', confirmation_status: 'confirmed_by_history' },
      'success',
      'confirmed',
      '2026-09-09T12:00:00',
    ),
    'UTC-123',
  );
});
