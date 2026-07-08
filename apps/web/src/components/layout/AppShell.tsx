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
    <div className="min-h-screen text-slate-100 selection:bg-cyan-500/30">
      <div className="mx-auto flex min-h-screen max-w-[1800px] gap-4 px-3 py-4 sm:gap-6 sm:px-6 md:gap-8 md:px-8 lg:px-10">
        <div className="hidden w-[300px] shrink-0 xl:block animate-in slide-in-from-left-8 duration-500">
          <Sidebar />
        </div>

        <div className={`fixed inset-0 z-50 xl:hidden transition-all duration-300 ${mobileOpen ? 'visible pointer-events-auto' : 'invisible pointer-events-none'}`}>
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            className={`absolute inset-0 w-full h-full bg-slate-950/40 backdrop-blur-sm transition-opacity duration-300 ${mobileOpen ? 'opacity-100' : 'opacity-0'}`}
            aria-label="close navigation"
          />
          <div
            className={`absolute right-4 top-4 h-[calc(100vh-2rem)] w-[min(320px,calc(100vw-2rem))] transition-all duration-300 origin-right ${
              mobileOpen ? 'opacity-100 translate-x-0 scale-100' : 'opacity-0 translate-x-full scale-95'
            }`}
          >
            <Sidebar onNavigate={() => setMobileOpen(false)} onClose={() => setMobileOpen(false)} />
          </div>
        </div>

        <main className="flex-1 py-2 flex flex-col gap-6 animate-in fade-in duration-700">
          <Header client={client} role={role} onLogout={handleLogout} onOpenMenu={() => setMobileOpen(true)} />
          <div className="relative flex-1">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
