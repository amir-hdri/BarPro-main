import type { QueryClient } from '@tanstack/react-query';
import type { StoredClient } from './auth';

type Identity = Pick<StoredClient, 'id' | 'role' | 'client_code'> | null;

export function sessionQueryKey(client: Identity, ...parts: readonly unknown[]) {
  return ['session', client?.role ?? 'anonymous', client?.id ?? client?.client_code ?? null, ...parts] as const;
}

export function clearSessionQueries(queryClient: QueryClient): void {
  // Cancel before clearing so a response from the previous account cannot refill
  // the cache after sign-out. Do not defer clear until the new session starts.
  void queryClient.cancelQueries();
  queryClient.clear();
}
