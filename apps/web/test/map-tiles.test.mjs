import test from 'node:test';
import assert from 'node:assert/strict';
import { createMapTiles } from '../src/lib/map-tiles.ts';

function fixture() {
  const layers = [];
  const changes = [];
  const L = { tileLayer: () => {
    const handlers = {};
    const layer = { on: (event, callback) => { handlers[event] = callback; }, off: () => {}, remove: () => {}, addTo: () => {}, handlers };
    layers.push(layer);
    return layer;
  } };
  const tiles = createMapTiles(L, {}, (theme, state) => changes.push([theme, state]));
  return { tiles, layers, changes };
}

test('failed providers are tried once and expose retry instead of an endless grey map', () => {
  const { tiles, layers, changes } = fixture();
  try {
    tiles.select();
    for (let index = 0; index < 2; index++) {
      for (let count = 0; count < 3; count++) layers[index].handlers.tileerror();
    }
    assert.equal(layers.length, 2);
    assert.deepEqual(changes.at(-1), ['osmStandard', 'unavailable']);
    tiles.select();
    assert.equal(layers.length, 3);
    assert.deepEqual(changes.at(-1), ['osm', 'loading']);
  } finally { tiles.dispose(); }
});

test('late events from a replaced or disposed layer cannot change displayed status', () => {
  const { tiles, layers, changes } = fixture();
  tiles.select();
  tiles.select('osmStandard');
  layers[0].handlers.tileload();
  assert.deepEqual(changes.at(-1), ['osmStandard', 'loading']);
  layers[1].handlers.tileload();
  assert.deepEqual(changes.at(-1), ['osmStandard', 'ready']);
  tiles.dispose();
  const count = changes.length;
  layers[1].handlers.tileload();
  assert.equal(changes.length, count);
});
