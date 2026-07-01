'use client'; // Error components must be Client Components

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    if (error.message?.includes('Failed to find Server Action') || 
        error.message?.includes('server action')) {
      const count = parseInt(sessionStorage.getItem('error_reload_count') || '0', 10);
      if (count >= 3) {
        console.warn('Max auto-reload attempts reached (3). Showing error page instead.');
      } else {
        sessionStorage.setItem('error_reload_count', String(count + 1));
        console.warn('Deployment mismatch detected, reloading the page...');
        window.location.reload();
      }
    } else {
      console.error('An unexpected error occurred:', error);
    }
  }, [error]);

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center p-4 text-center">
      <div className="max-w-md rounded-xl border border-red-100 bg-red-50/50 p-8 shadow-sm backdrop-blur-sm dark:border-red-900/20 dark:bg-red-900/10">
        <div className="mb-4 flex justify-center">
          <div className="rounded-full bg-red-100 p-3 text-red-600 dark:bg-red-900/30 dark:text-red-400">
            <svg xmlns="http://www.w3.org/2000/svg" className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
        </div>
        <h2 className="mb-2 text-xl font-bold text-slate-800 dark:text-slate-200">خطایی رخ داد</h2>
        <p className="mb-6 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
          {error.message?.includes('Failed to find Server Action')
            ? 'سیستم بروزرسانی شده است. در حال بارگذاری مجدد صفحه...'
            : 'متأسفانه در پردازش درخواست شما مشکلی پیش آمد. لطفاً دوباره تلاش کنید.'}
        </p>
        <button
          onClick={() => reset()}
          className="inline-flex items-center justify-center rounded-lg bg-red-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 disabled:opacity-50 dark:hover:bg-red-500"
        >
          تلاش مجدد
        </button>
      </div>
    </div>
  );
}
