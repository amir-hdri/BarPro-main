import test from 'node:test';
import assert from 'node:assert/strict';

// Mirror of validatePinCoords in @/schemas/waybillSchema.ts — kept in sync
// by test. If the schema helper changes, this test must change with it.
function validatePinCoords(value) {
  if (!value || typeof value !== 'object') return false;
  const lat = Number(value.lat);
  const lng = Number(value.lng);
  return (
    Number.isFinite(lat) &&
    Number.isFinite(lng) &&
    lat >= -90 &&
    lat <= 90 &&
    lng >= -180 &&
    lng <= 180 &&
    !(lat === 0 && lng === 0)
  );
}

test('nullish pins are rejected', () => {
  assert.equal(validatePinCoords(null), false);
  assert.equal(validatePinCoords(undefined), false);
  assert.equal(validatePinCoords('35,51'), false);
});

test('out-of-range and zero pins are rejected', () => {
  assert.equal(validatePinCoords({ lat: 99.9, lng: 51.3 }), false);
  assert.equal(validatePinCoords({ lat: 35.6, lng: 199.9 }), false);
  assert.equal(validatePinCoords({ lat: 0, lng: 0 }), false);
  assert.equal(validatePinCoords({ lat: NaN, lng: 51.3 }), false);
});

test('real pins are accepted', () => {
  assert.equal(validatePinCoords({ lat: 35.6892, lng: 51.389 }), true);
  assert.equal(validatePinCoords({ lat: -33.86, lng: 151.2 }), true);
});

// Mirror of the GPS-anchor extraction order in @/lib/format.ts
// (flat originLat keys first, then metadata coordinates, never a guess).
function extractAnchors(payload) {
  const numOrNull = (value) => {
    const num = typeof value === 'number' ? value : Number(value);
    return Number.isFinite(num) ? num : null;
  };
  const coordsOrNull = (value) => {
    if (!value || typeof value !== 'object') return null;
    const lat = numOrNull(value.lat ?? value.latitude);
    const lng = numOrNull(value.lng ?? value.lon ?? value.longitude);
    if (lat === null || lng === null || (lat === 0 && lng === 0)) return null;
    return { lat, lng };
  };
  let meta = null;
  if (payload.metadata_json && typeof payload.metadata_json === 'object') {
    meta = payload.metadata_json;
  } else if (typeof payload.metadata_json === 'string') {
    try {
      meta = JSON.parse(payload.metadata_json);
    } catch {
      meta = null;
    }
  }
  const metaOrigin = meta?.origin ?? null;
  const metaDest = meta?.destination ?? null;
  return {
    origin:
      (numOrNull(payload.originLat) !== null && numOrNull(payload.originLng) !== null
        ? { lat: numOrNull(payload.originLat), lng: numOrNull(payload.originLng) }
        : null) ?? coordsOrNull(metaOrigin?.coordinates) ?? null,
    destination:
      (numOrNull(payload.destLat) !== null && numOrNull(payload.destLng) !== null
        ? { lat: numOrNull(payload.destLat), lng: numOrNull(payload.destLng) }
        : null) ?? coordsOrNull(metaDest?.coordinates) ?? null,
  };
}

test('anchor extraction reads metadata coordinates for new-form jobs', () => {
  const anchors = extractAnchors({
    origin: 'مشهد',
    metadata_json: {
      origin: { city: 'مشهد', coordinates: { lat: 36.29, lng: 59.6 } },
      destination: { city: 'تهران', coordinates: { lat: 35.68, lng: 51.38 } },
    },
  });
  assert.deepEqual(anchors.origin, { lat: 36.29, lng: 59.6 });
  assert.deepEqual(anchors.destination, { lat: 35.68, lng: 51.38 });
});

test('anchor extraction stays null for legacy jobs without pins', () => {
  const anchors = extractAnchors({ origin: 'مشهد', destination: 'تهران' });
  assert.equal(anchors.origin, null);
  assert.equal(anchors.destination, null);
});
