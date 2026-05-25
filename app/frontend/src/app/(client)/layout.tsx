"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  Truck,
  Calendar,
  FileText,
  AlertTriangle,
  BarChart3,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { api } from "@/lib/api";
import { ClientUser, DashboardStats as ClientDashboardStats } from "@/lib/types";

const clientNavItems = [
  { href: "/client/dashboard", label: "داشبورد", icon: LayoutDashboard },
  { href: "/client/drivers", label: "رانندگان و پلاک", icon: Truck },
  { href: "/client/schedules", label: "زمان‌بندی", icon: Calendar },
  { href: "/client/waybills", label: "بارنامه‌ها", icon: FileText },
  { href: "/client/reports", label: "گزارش‌ها", icon: BarChart3 },
  { href: "/client/errors", label: "خطاها", icon: AlertTriangle },
];

export default function ClientLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<ClientUser | null>(null);

  useEffect(() => {
    const role = localStorage.getItem("utcms_role");
    if (role !== "client") router.push("/login");
    api.get<ClientUser>("/api/v1/auth/me").then((res) => {
      if (res.data) setUser(res.data);
    });
  }, [router]);

  function handleLogout() {
    localStorage.removeItem("utcms_role");
    api.clearToken();
    window.location.href = "/login";
  }

  const activeNav = clientNavItems.find((item) => pathname === item.href);

  return (
    <div className="flex min-h-screen bg-gradient-to-br from-indigo-900 via-slate-900 to-purple-900">
      {/* Sidebar */}
      <aside className={`fixed inset-y-0 right-0 z-50 w-64 transform border-r border-white/10 bg-slate-900/80 backdrop-blur-xl transition-transform duration-300 md:translate-x-0 ${
        mobileOpen ? "translate-x-0" : "translate-x-full"
      }`}>
        <div className="flex h-full flex-col">
          <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
            <h2 className="text-lg font-bold text-slate-100">UTCMS Pro</h2>
            <button onClick={() => setMobileOpen(false)} className="md:hidden text-slate-400 hover:text-slate-100">
              <X className="h-5 w-5" />
            </button>
          </div>
          <nav className="flex-1 space-y-1 px-3 py-4">
            {clientNavItems.map((item) => {
              const Icon = item.icon;
              const isActive = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={`flex items-center gap-3 rounded-xl px-4 py-3 text-sm font-medium transition-all ${
                    isActive
                      ? "bg-gradient-to-r from-cyan-500/20 to-amber-400/20 text-cyan-300"
                      : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                  }`}
                >
                  <Icon className="h-5 w-5" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="border-t border-white/10 p-4">
            {user && (
              <div className="mb-3 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-r from-cyan-500 to-amber-400 text-sm font-bold text-slate-950">
                  {user.name.slice(0, 2)}
                </div>
                <div>
                  <p className="text-sm font-medium text-slate-100">{user.name}</p>
                  <p className="text-xs text-slate-400">کاربر</p>
                </div>
              </div>
            )}
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-xl px-4 py-2.5 text-sm text-slate-400 transition-all hover:bg-red-500/10 hover:text-red-400"
            >
              <LogOut className="h-5 w-5" />
              خروج
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 md:mr-64">
        <header className="sticky top-0 z-40 border-b border-white/10 bg-slate-900/80 backdrop-blur-xl px-4 py-3 md:px-6">
          <div className="flex items-center justify-between">
            <button onClick={() => setMobileOpen(true)} className="md:hidden text-slate-400 hover:text-slate-100">
              <Menu className="h-6 w-6" />
            </button>
            <h1 className="text-lg font-semibold text-slate-100">{activeNav?.label || "پنل کاربری"}</h1>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-400"></span>
                آنلاین
              </span>
            </div>
          </div>
        </header>
        <main className="p-4 md:p-6">{children}</main>
      </div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm md:hidden" onClick={() => setMobileOpen(false)} />
      )}
    </div>
  );
}
