import test from 'node:test';
import assert from 'node:assert/strict';
import { QueryClient, QueryObserver } from '@tanstack/react-query';
import { sessionQueryKey, clearSessionQueries } from '../src/lib/session-query.ts';

const tenant = (id) => ({ id, role: 'client', client_code: `tenant-${id}` });

test('fresh sensitive cache from account A is never served as account B', async () => {
  const queryClient = new QueryClient();
  const calls = [];
  const options = (id) => ({
    queryKey: sessionQueryKey(tenant(id), 'drivers'), staleTime: 120000,
    queryFn: async () => { calls.push(id); return [{ client_id: id }]; },
  });
  await queryClient.fetchQuery(options(1));
  const observer = new QueryObserver(queryClient, options(2));
  assert.equal(observer.getCurrentResult().data, undefined);
  assert.deepEqual(await queryClient.fetchQuery(options(2)), [{ client_id: 2 }]);
  assert.deepEqual(calls, [1, 2]);
  queryClient.clear();
});

test('sign-out cancels an in-flight request and does not let it refill sensitive cache', async () => {
  const queryClient = new QueryClient();
  let finish;
  let signal;
  const key = sessionQueryKey(tenant(1), 'drivers');
  const pending = queryClient.fetchQuery({ queryKey: key, queryFn: ({ signal: requestSignal }) => {
    signal = requestSignal;
    return new Promise((resolve) => { finish = resolve; });
  }}).catch(() => undefined);
  clearSessionQueries(queryClient);
  assert.equal(signal.aborted, true);
  finish([{ client_id: 1 }]);
  await pending;
  assert.equal(queryClient.getQueryData(key), undefined);
  assert.equal(queryClient.getQueryCache().getAll().length, 0);
});

test('admin and anonymous cache keys cannot overlap a tenant key', () => {
  assert.notDeepEqual(sessionQueryKey(null, 'drivers'), sessionQueryKey(tenant(1), 'drivers'));
  assert.notDeepEqual(sessionQueryKey({ id: null, role: 'master_admin', client_code: 'admin' }, 'drivers'), sessionQueryKey(tenant(1), 'drivers'));
});
