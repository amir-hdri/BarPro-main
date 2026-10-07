// Real installed QueryClient/QueryObserver, synthetic API identities, no browser or network.
// Confirms the cache mechanism; the end-to-end browser account switch was inconclusive.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { QueryClient, QueryObserver } from '../../../apps/web/node_modules/@tanstack/query-core/build/modern/index.js';

const source = readFileSync(new URL('../../../apps/web/src/app/drivers/page.tsx', import.meta.url), 'utf8');
assert.match(source, /queryKey: \['drivers'\]/);
const staleTime = Number(source.match(/staleTime: (\d+)/)[1]);
const client = new QueryClient();
let tenant = 'A';
const calls = [];
const options = () => ({
  queryKey: ['drivers'], staleTime,
  queryFn: async () => { calls.push(tenant); return [{ client_id: tenant, full_name: `Audit Driver ${tenant}` }]; },
});
await client.fetchQuery(options());
// QueryProvider stays mounted across App Router navigation. clearSession/persistSession
// only update localStorage/session events; neither clears this QueryClient.
tenant = 'B';
const observer = new QueryObserver(client, options());
const unsubscribe = observer.subscribe(() => {});
const observed = observer.getCurrentResult();
assert.equal(observed.data[0].client_id, 'A');
assert.deepEqual(calls, ['A']);
console.log(JSON.stringify({ case: 'tenant_switch_on_same_query_client', signed_in_tenant: tenant, displayed_cached_tenant: observed.data[0].client_id, api_requests: calls, stale_time_ms: staleTime, evidence_level: 'runtime_library_reproduction_plus_source_trace_not_browser_e2e' }));
unsubscribe();
client.clear();
