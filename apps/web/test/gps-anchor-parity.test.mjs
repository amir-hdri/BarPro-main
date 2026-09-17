import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { parseWaybillPayload } from '../src/lib/format.ts';

const cases = JSON.parse(readFileSync(new URL('../../../tests/fixtures/gps_anchor_cases.json', import.meta.url), 'utf8'));
for (const example of cases) {
  test(example.name, () => {
    const result = parseWaybillPayload(example.payload);
    assert.deepEqual(result.originCoords, example.origin);
    assert.deepEqual(result.destinationCoords, example.destination);
  });
}
