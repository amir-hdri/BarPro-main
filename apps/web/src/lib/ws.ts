/**
 * Utility function to build WebSocket URLs cleanly across development and production environments.
 */
export function buildWebSocketUrl(
  path: string = '/ws/waybill',
  query?: Record<string, string | undefined | null>
): string {
  try {
    if (typeof window !== 'undefined') {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.port === '3000'
        ? `${window.location.hostname}:8000`
        : window.location.host;

      const cleanPath = path.startsWith('/') ? path : `/${path}`;
      const url = new URL(`${protocol}//${host}${cleanPath}`);

      if (query) {
        for (const [key, value] of Object.entries(query)) {
          if (value !== undefined && value !== null && value !== '') {
            url.searchParams.append(key, value);
          }
        }
      }

      return url.toString();
    }
  } catch {
    // Fallback for SSR or invalid location
  }

  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const url = new URL(`ws://127.0.0.1:8000${cleanPath}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.append(key, value);
      }
    }
  }
  return url.toString();
}
