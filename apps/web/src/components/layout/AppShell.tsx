'use client';

import { useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';

import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { useSession } from '@/hooks/useSession';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const router = useRouter();
  const { client, logout, role } = useSession();

  const handleLogout = () => {
    logout();
    router.push('/auth');
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.15),_transparent_30%),linear-gradient(135deg,_#f8fafc_0%,_#e2e8f0_45%,_#fff7ed_100%)] text-slate-900">
      <div className="mx-auto flex min-h-screen max-w-[1600px] gap-6 px-4 py-4 md:px-6 lg:px-8">
        <div className="hidden w-[320px] shrink-0 xl:block">
          <Sidebar />
        </div>

        {mobileOpen && (
          <div className="fixed inset-0 z-50 xl:hidden">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute inset-0 bg-slate-950/60"
              aria-label="close navigation"
            />
            <div className="absolute right-4 top-4 h-[calc(100vh-2rem)] w-[min(320px,calc(100vw-2rem))]">
              <Sidebar onNavigate={() => setMobileOpen(false)} />
            </div>
          </div>
        )}

        <main className="flex-1 py-1">
          <Header client={client} role={role} onLogout={handleLogout} onOpenMenu={() => setMobileOpen(true)} />
          {children}
        </main>
      </div>
    </div>
  );
}
