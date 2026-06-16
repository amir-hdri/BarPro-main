import type { Metadata } from 'next';
import localFont from 'next/font/local';

import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';
import { Toaster } from 'react-hot-toast';

const rubik = localFont({
  src: '../../public/fonts/Rubik-Regular.ttf',
  variable: '--font-rubik',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'UTCMS Automation Console',
  description: 'پنل عملیاتی فارسی برای مدیریت رانندگان، صف بارنامه و گزارش‌های چندمستاجره',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl" className={rubik.variable} suppressHydrationWarning>
      <body className="font-sans antialiased text-slate-200" suppressHydrationWarning>
        <QueryProvider>
          {children}
          <Toaster position="bottom-center" />
        </QueryProvider>
      </body>
    </html>
  );
}
