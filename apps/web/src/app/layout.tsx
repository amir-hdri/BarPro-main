import type { Metadata, Viewport } from 'next';
import localFont from 'next/font/local';

import './globals.css';
import { QueryProvider } from '@/providers/QueryProvider';
import { Toaster } from 'react-hot-toast';

const rubik = localFont({
  src: '../../public/fonts/Rubik-Regular.ttf',
  variable: '--font-rubik',
  display: 'swap',
});

const vazirmatn = localFont({
  src: '../../public/fonts/Vazirmatn-Variable.ttf',
  variable: '--font-vazirmatn',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'UTCMS Automation Console',
  description: 'پنل عملیاتی فارسی برای مدیریت رانندگان، صف بارنامه و گزارش‌های چندمستاجره',
};

export const viewport: Viewport = {
  themeColor: '#030712',
  viewportFit: 'cover',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl" className={`${vazirmatn.variable} ${rubik.variable}`} suppressHydrationWarning>
      <body className="font-sans antialiased text-slate-200" suppressHydrationWarning>
        <QueryProvider>
          {children}
          <Toaster position="bottom-center" />
        </QueryProvider>
      </body>
    </html>
  );
}
