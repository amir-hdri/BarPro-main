"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { AuthGuard } from "@/components/layout/AuthGuard";
import { useSession } from "@/hooks/useSession";
import { api } from "@/lib/api";
import {
  LayoutDashboard,
  Users,
  BarChart3,
  FileText,
  LogOut,
  Menu,
  X,
  ChevronLeft,
  Shield,
  Server,
} from "lucide-react";

const adminNavItems = [
  { href: "/admin/dashboard", label: "داشبورد", icon: LayoutDashboard, description: "آمار کلی سیستم" },
  { href: "/admin/clients", label: "مدیریت کاربران", icon: Users, description: "افزودن و ویرایش کاربران" },
  { href: "/admin/reports", label: "گزارش عملکرد", icon: BarChart3, description: "تحلیل داده‌های سیستم" },
  { href: "/admin/audit", label: "لاگ فعالیت‌ها", icon: FileText, description: "تاریخچه اقدامات" },
  { href: "/admin/health", label: "سلامت سیستم", icon: Server, description: "مانیتورینگ سرور و زیرساخت" },
];


export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [stats, setStats] = useState<{ clients: number; logs: number } | null>(null);
  const { client, logout } = useSession();

  // Fetch client summary and audit logs counts on mount
  useEffect(() => {
    api.get<any>("/api/v1/admin/reports/clients/summary")
      .then((res) => {
        if (res.data) {
          // If response has total_clients field, use it, otherwise count the items in the list
          const totalClients = res.data.total_clients || (res.data.items ? res.data.items.length : 0);
          setStats((prev) => ({
            clients: totalClients,
            logs: prev?.logs || 0,
          }));
        }
      })
      .catch(() => {});

    api.get<any>("/api/v1/admin/reports/audit-logs?page_size=1")
      .then((res) => {
        if (res.data) {
          // Using standard list counts or estimating
          const totalLogs = res.data.items?.length || 0;
          setStats((prev) => ({
            clients: prev?.clients || 0,
            logs: totalLogs,
          }));
        }
      })
      .catch(() => {});
  }, []);

  // Close sidebar on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Prevent body scroll when sidebar is open on mobile
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [mobileOpen]);

  function handleLogout() {
    logout();
    router.push("/auth");
  }

  const activeNav = adminNavItems.find((item) => pathname?.startsWith(item.href));

  return (
    <AuthGuard requiredRole="master_admin">
      <div className="flex min-h-screen bg-gradient-to-br from-indigo-950 via-slate-900 to-purple-950" dir="rtl">

        {/* ── Mobile overlay ───────────────────────── */}
        <div
          onClick={() => setMobileOpen(false)}
          className={`fixed inset-0 z-40 bg-black/60 backdrop-blur-sm transition-all duration-300 md:hidden ${
            mobileOpen ? "opacity-100 visible pointer-events-auto" : "opacity-0 invisible pointer-events-none"
          }`}
          aria-hidden="true"
        />

        {/* ── Sidebar ──────────────────────────────── */}
        <aside
          className={`fixed inset-y-0 right-0 z-50 flex w-[280px] flex-col border-l border-white/10 bg-slate-900/95 backdrop-blur-2xl shadow-2xl transition-transform duration-300 ease-in-out md:translate-x-0 ${
            mobileOpen ? "translate-x-0" : "translate-x-full md:translate-x-0"
          }`}
        >
          {/* Sidebar header */}
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-amber-400 shadow-lg">
                <Shield className="h-5 w-5 text-slate-950" />
              </div>
              <div>
                <h2 className="text-base font-black text-slate-100 leading-none">BarPro</h2>
                <p className="text-[10px] text-slate-400 mt-0.5">پنل مدیریت</p>
              </div>
            </div>
            <button
              onClick={() => setMobileOpen(false)}
              className="md:hidden rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-slate-100 transition-colors"
              aria-label="بستن منو"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          {/* Nav items */}
          <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">
            {adminNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href || pathname?.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`group flex items-center gap-3 rounded-2xl px-4 py-3.5 text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? "bg-gradient-to-r from-cyan-500/20 to-amber-400/10 text-cyan-300 shadow-sm"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  }`}
                >
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-xl transition-colors ${
                    isActive ? "bg-cyan-500/20 text-cyan-300" : "bg-white/5 text-slate-500 group-hover:bg-white/10 group-hover:text-slate-300"
                  }`}>
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="flex-1 min-w-0 flex items-center justify-between gap-2">
                    <div>
                      <div className="font-semibold truncate">{item.label}</div>
                      <div className="text-[10px] text-slate-500 truncate mt-0.5">{item.description}</div>
                    </div>
                    {item.href === "/admin/clients" && stats && stats.clients > 0 && (
                      <span className="inline-flex items-center justify-center px-2 py-0.5 text-[10px] font-bold rounded-full bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 shrink-0">
                        {stats.clients}
                      </span>
                    )}
                    {item.href === "/admin/audit" && stats && stats.logs > 0 && (
                      <span className="inline-flex items-center justify-center px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20 shrink-0">
                        {stats.logs}
                      </span>
                    )}
                  </div>
                  {isActive && <ChevronLeft className="h-4 w-4 text-cyan-400/60 shrink-0" />}
                </Link>
              );
            })}
          </nav>

          {/* User section */}
          <div className="border-t border-white/10 p-4 space-y-3">
            <div className="flex items-center gap-3 px-2 py-2 rounded-2xl bg-white/5">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500 to-amber-400 text-sm font-black text-slate-950 shadow">
                {(client?.name || "مدیر").slice(0, 2)}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-slate-100 truncate">{client?.name || "مدیر سیستم"}</p>
                <p className="text-[10px] text-emerald-400">● آنلاین · مدیر ارشد</p>
              </div>
            </div>
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-sm text-slate-400 transition-all hover:bg-red-500/10 hover:text-red-400 group"
            >
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/5 group-hover:bg-red-500/10 transition-colors">
                <LogOut className="h-4 w-4" />
              </div>
              خروج از سیستم
            </button>
          </div>
        </aside>

        {/* ── Main content ──────────────────────────── */}
        <div className="flex flex-1 flex-col md:mr-[280px] min-w-0">

          {/* Top header */}
          <header className="sticky top-0 z-30 border-b border-white/10 bg-slate-900/80 backdrop-blur-xl">
            <div className="flex items-center gap-3 px-4 py-3 md:px-6">
              {/* Mobile menu toggle */}
              <button
                onClick={() => setMobileOpen(true)}
                className="md:hidden flex h-9 w-9 items-center justify-center rounded-xl bg-white/5 text-slate-400 hover:bg-white/10 hover:text-slate-100 transition-colors"
                aria-label="باز کردن منو"
              >
                <Menu className="h-5 w-5" />
              </button>

              {/* Page title */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  {activeNav && (
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-400">
                      <activeNav.icon className="h-4 w-4" />
                    </div>
                  )}
                  <h1 className="text-base font-bold text-slate-100 truncate">
                    {activeNav?.label || "پنل مدیریت"}
                  </h1>
                </div>
              </div>

              {/* Header actions */}
              <div className="flex items-center gap-2">
                <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 px-3 py-1 text-xs font-medium text-emerald-300">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  آنلاین
                </span>
                {/* Logout shortcut on mobile header */}
                <button
                  onClick={handleLogout}
                  className="md:hidden flex h-9 w-9 items-center justify-center rounded-xl bg-white/5 text-slate-400 hover:bg-red-500/10 hover:text-red-400 transition-colors"
                  aria-label="خروج از سیستم"
                  title="خروج از سیستم"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Mobile breadcrumb nav */}
            <div className="flex gap-1 overflow-x-auto scrollbar-none border-t border-white/5 px-4 py-2 md:hidden">
              {adminNavItems.map((item) => {
                const Icon = item.icon;
                const isActive = pathname?.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-medium transition-colors ${
                      isActive
                        ? "bg-cyan-500/15 text-cyan-300"
                        : "bg-white/5 text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5" />
                    {item.label}
                  </Link>
                );
              })}
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 p-4 md:p-6 lg:p-8">
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
