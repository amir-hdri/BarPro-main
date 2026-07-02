'use client';

import { useState, useEffect } from 'react';

import {
  AUTH_CLIENT_KEY,
  AUTH_SESSION_EVENT,
  AUTH_TOKEN_KEY,
  clearSession,
  type StoredClient,
} from '@/lib/auth';

interface SessionSnapshot {
  client: StoredClient | null;
  token: string | null;
}

function readClientFromStorage(): StoredClient | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const rawValue = window.localStorage.getItem(AUTH_CLIENT_KEY);
    if (!rawValue) {
      return null;
    }
    return JSON.parse(rawValue) as StoredClient;
  } catch (e) {
    console.error('Failed to read client from storage:', e);
    return null;
  }
}

export function useSession() {
  const [session, setSession] = useState<SessionSnapshot>({ client: null, token: null });
  const [isReady, setIsReady] = useState(false);

  useEffect(() => {
    try {
      // Read initial session on mount (client-side only)
      const client = readClientFromStorage();
      const token = window.localStorage.getItem(AUTH_TOKEN_KEY);
      setSession({ client, token });
    } catch (e) {
      console.error('Failed to read session from storage:', e);
    } finally {
      setIsReady(true);
    }

    const handler = () => {
      try {
        const updatedClient = readClientFromStorage();
        const updatedToken = window.localStorage.getItem(AUTH_TOKEN_KEY);
        setSession({ client: updatedClient, token: updatedToken });
      } catch (e) {
        console.error('Failed to update session from storage:', e);
      }
    };

    window.addEventListener('storage', handler);
    window.addEventListener(AUTH_SESSION_EVENT, handler);

    return () => {
      window.removeEventListener('storage', handler);
      window.removeEventListener(AUTH_SESSION_EVENT, handler);
    };
  }, []);

  const role = session.client?.role ?? null;

  return {
    client: session.client,
    isAuthenticated: Boolean(session.client),
    isAdmin: role === 'master_admin',
    isClient: role === 'client',
    isReady: isReady,
    logout: clearSession,
    role,
    token: session.token,
  };
}
