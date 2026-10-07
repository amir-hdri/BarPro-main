import test from 'node:test';
import assert from 'node:assert/strict';
import { copyText } from '../src/lib/clipboard.ts';

test('copy succeeds only after the asynchronous clipboard write resolves', async () => {
  let finish;
  let settled = false;
  const result = copyText('audit-url', { writeClipboard: () => new Promise((resolve) => { finish = resolve; }), fallback: () => false });
  result.then(() => { settled = true; });
  await Promise.resolve();
  assert.equal(settled, false);
  finish();
  assert.equal(await result, true);
});

test('HTTP without Clipboard API uses the legacy copy path', async () => {
  let copied;
  assert.equal(await copyText('audit-url', { fallback: (text) => { copied = text; return true; } }), true);
  assert.equal(copied, 'audit-url');
});

test('permission rejection tries fallback and never claims success if both fail', async () => {
  const writeClipboard = async () => { throw new Error('NotAllowedError'); };
  assert.equal(await copyText('audit-url', { writeClipboard, fallback: () => false }), false);
  assert.equal(await copyText('audit-url', { writeClipboard, fallback: () => { throw new Error('copy unsupported'); } }), false);
});
