import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "UTCMS Pro Dashboard | داشبورد حرفه‌ای",
  description: "سامانه هوشمند مدیریت بارنامه",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fa" dir="rtl" className="dark">
      <body className="font-sans antialiased">
        {/* Animated background layer */}
        <div className="fixed inset-0 -z-10 bg-gradient-to-br from-indigo-900 via-slate-900 to-purple-900 opacity-20"></div>
        {children}
      </body>
    </html>
  );
}
