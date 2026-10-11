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
    for (let index = 0; index < 4; index++) {
      for (let count = 0; count < 3; count++) layers[index].handlers.tileerror();
    }
    assert.equal(layers.length, 4);
    assert.deepEqual(changes.at(-1), ['google', 'unavailable']);
    tiles.select();
    assert.equal(layers.length, 5);
    assert.deepEqual(changes.at(-1), ['osmDe', 'loading']);
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

test('fallback order iterates through all key-free providers sequentially', () => {
  const { tiles, layers, changes } = fixture();
  try {
    tiles.select();
    assert.deepEqual(changes, [['osmDe', 'loading']]);
    for (let count = 0; count < 3; count++) layers[0].handlers.tileerror();
    assert.deepEqual(changes.slice(1, 2), [['osmStandard', 'loading']]);
    for (let count = 0; count < 3; count++) layers[1].handlers.tileerror();
    assert.deepEqual(changes.slice(2, 3), [['osmHot', 'loading']]);
    for (let count = 0; count < 3; count++) layers[2].handlers.tileerror();
    assert.deepEqual(changes.slice(3, 4), [['google', 'loading']]);
    for (let count = 0; count < 3; count++) layers[3].handlers.tileerror();
    assert.deepEqual(changes.slice(4, 5), [['google', 'unavailable']]);
  } finally { tiles.dispose(); }
});

test('successful load on fallback layer transitions to ready', () => {
  const { tiles, layers, changes } = fixture();
  try {
    tiles.select();
    assert.deepEqual(changes, [['osmDe', 'loading']]);
    for (let count = 0; count < 3; count++) layers[0].handlers.tileerror();
    assert.deepEqual(changes.slice(1, 2), [['osmStandard', 'loading']]);
    layers[1].handlers.tileload();
    assert.deepEqual(changes.slice(2, 3), [['osmStandard', 'ready']]);
  } finally { tiles.dispose(); }
});

test('timeout triggers fallback when tiles stall without error', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const { tiles, changes } = fixture();
  try {
    tiles.select();
    assert.deepEqual(changes, [['osmDe', 'loading']]);
    t.mock.timers.tick(8000);
    assert.deepEqual(changes.slice(1, 2), [['osmStandard', 'loading']]);
  } finally {
    tiles.dispose();
    t.mock.timers.reset();
  }
});

