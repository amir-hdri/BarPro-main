'use client';

import { useState, useEffect, type ReactNode } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';

import { Header } from '@/components/layout/Header';
import { Sidebar } from '@/components/layout/Sidebar';
import { useSession } from '@/hooks/useSession';

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const router = useRouter();
  const pathname = usePathname();
  const { client, logout, role } = useSession();

  // Close mobile menu on path changes
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Lock body scroll when mobile menu is open
  useEffect(() => {
    document.body.style.overflow = mobileOpen ? 'hidden' : '';
    return () => {
      document.body.style.overflow = '';
    };
  }, [mobileOpen]);

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

        <AnimatePresence>
          {mobileOpen && (
            <div className="fixed inset-0 z-50 xl:hidden">
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.2 }}
                onClick={() => setMobileOpen(false)}
                className="absolute inset-0 bg-slate-950/40 backdrop-blur-sm"
              />
              
              {/* Sliding Drawer */}
              <motion.div
                drag="x"
                dragConstraints={{ left: 0, right: 0 }}
                dragElastic={{ left: 0, right: 0.4 }}
                onDragEnd={(_, info) => {
                  // Sliding to the right (offset x > 80) closes it in RTL
                  if (info.offset.x > 80) {
                    setMobileOpen(false);
                  }
                }}
                initial={{ x: '100%', opacity: 0.9 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ x: '100%', opacity: 0.9 }}
                transition={{ type: 'spring', damping: 30, stiffness: 350 }}
                className="absolute right-4 top-4 h-[calc(100vh-2rem)] w-[min(320px,calc(100vw-2rem))] z-10"
              >
                <Sidebar onNavigate={() => setMobileOpen(false)} onClose={() => setMobileOpen(false)} />
              </motion.div>
            </div>
          )}
        </AnimatePresence>

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
