"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Fragment, useEffect, useState, type ReactNode } from "react";
import { AUTH_CLIENT_KEY, AUTH_SESSION_EVENT } from '@/lib/auth';
import { clearSessionQueries } from '@/lib/session-query';

interface QueryProviderProps {
  children: ReactNode;
}

export function QueryProvider({ children }: QueryProviderProps) {
  const [sessionVersion, setSessionVersion] = useState(0);
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000,
            gcTime: 5 * 60 * 1000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  useEffect(() => {
    const onSessionChange = () => {
      clearSessionQueries(queryClient);
      // Forms, dialogs and polling also hold tenant data outside React Query.
      // Unmount them with the old session so local state cannot cross accounts.
      setSessionVersion(version => version + 1);
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === AUTH_CLIENT_KEY || event.key === null) onSessionChange();
    };
    window.addEventListener(AUTH_SESSION_EVENT, onSessionChange);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener(AUTH_SESSION_EVENT, onSessionChange);
      window.removeEventListener('storage', onStorage);
    };
  }, [queryClient]);

  return (
    <QueryClientProvider client={queryClient}>
      <Fragment key={sessionVersion}>{children}</Fragment>
    </QueryClientProvider>
  );
}
