import type { Metadata, Viewport } from 'next';
import localFont from 'next/font/local';

import './globals.css';
import { ErrorBoundary } from '@/components/ErrorBoundary';
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
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  themeColor: '#030712',
  viewportFit: 'cover',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fa" dir="rtl" className={`${vazirmatn.variable} ${rubik.variable}`} suppressHydrationWarning>
      <head>
        {/* Map tile CDN: preconnect once so first Leaflet paint never waits on DNS/TLS. */}
        <link rel="preconnect" href="https://a.basemaps.cartocdn.com" crossOrigin="anonymous" />
        <link rel="preconnect" href="https://b.basemaps.cartocdn.com" crossOrigin="anonymous" />
        <link rel="dns-prefetch" href="https://c.basemaps.cartocdn.com" />
        <link rel="dns-prefetch" href="https://d.basemaps.cartocdn.com" />
      </head>
      <body className="font-sans antialiased text-slate-200" suppressHydrationWarning>
        <QueryProvider>
          <ErrorBoundary>
            {children}
          </ErrorBoundary>
          <Toaster position="bottom-center" />
        </QueryProvider>
      </body>
    </html>
  );
}
