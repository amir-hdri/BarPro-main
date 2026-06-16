import type { Metadata } from 'next';
import { Vazirmatn } from 'next/font/google';

import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';
import { Toaster } from 'react-hot-toast';

const vazirmatn = Vazirmatn({ 
  subsets: ['arabic', 'latin'],
  display: 'swap',
  variable: '--font-vazirmatn',
});

export const metadata: Metadata = {
  title: 'UTCMS Automation Console',
  description: 'پنل عملیاتی فارسی برای مدیریت رانندگان، صف بارنامه و گزارش‌های چندمستاجره',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl" className={vazirmatn.variable} suppressHydrationWarning>
      <body className="font-sans antialiased text-slate-800" suppressHydrationWarning>
        <QueryProvider>
          {children}
          <Toaster position="bottom-center" />
        </QueryProvider>
      </body>
    </html>
  );
}
