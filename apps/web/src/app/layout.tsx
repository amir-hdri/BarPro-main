import type { Metadata } from 'next';

import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';
import { Toaster } from 'react-hot-toast';

export const metadata: Metadata = {
  title: 'UTCMS Automation Console',
  description: 'پنل عملیاتی فارسی برای مدیریت رانندگان، صف بارنامه و گزارش‌های چندمستاجره',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl">
      <body>
        <QueryProvider>
          {children}
          <Toaster />
        </QueryProvider>
      </body>
    </html>
  );
}
