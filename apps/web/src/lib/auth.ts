import { post } from './api';

export const AUTH_CLIENT_KEY = 'utcms_auth_client';
export const AUTH_SESSION_EVENT = 'utcms:session-change';

const LEGACY_AUTH_TOKEN_KEYS = [
  'utcms_auth_token',
  'utcms_token',
  'access_token',
  'token',
] as const;

export type StoredRole = 'client' | 'master_admin';

export interface StoredClient {
  id: number | null;
  name: string;
  email: string;
  client_code: string;
  role: StoredRole;
}

function clearLegacyAuthTokens(): void {
  for (const key of LEGACY_AUTH_TOKEN_KEYS) {
    window.localStorage.removeItem(key);
  }
}

export function getStoredClient(): StoredClient | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    clearLegacyAuthTokens();
    const rawValue = window.localStorage.getItem(AUTH_CLIENT_KEY);
    if (!rawValue) {
      return null;
    }
    return JSON.parse(rawValue) as StoredClient;
  } catch (e) {
    console.error('Failed to get stored client:', e);
    return null;
  }
}

export function persistSession(client: StoredClient): void {
  if (typeof window === 'undefined') {
    return;
  }

  try {
    clearLegacyAuthTokens();
    window.localStorage.setItem(AUTH_CLIENT_KEY, JSON.stringify(client));
    window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
  } catch (e) {
    console.error('Failed to persist session:', e);
  }
}

export function clearSession(): void {
  if (typeof window === 'undefined') {
    return;
  }

  post('/api/v1/auth/logout').catch(() => {});

  try {
    clearLegacyAuthTokens();
    window.localStorage.removeItem(AUTH_CLIENT_KEY);
    window.dispatchEvent(new Event(AUTH_SESSION_EVENT));
  } catch (e) {
    console.error('Failed to clear session:', e);
  }
}
