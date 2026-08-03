"use client";

import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("ErrorBoundary caught an error:", error, errorInfo);
  }

  public render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }
      return (
        <div className="flex flex-col items-center justify-center min-h-screen p-4">
          <h1 className="text-2xl font-bold text-red-500 mb-4">خطایی رخ داده است</h1>
          <p className="text-gray-400 text-center">
            متاسفیم، خطایی در برنامه رخ داده است. لطفاً صفحه را Refresh کنید یا با پشتیبانی تماس بگیرید.
          </p>
          <details className="mt-4 p-4 bg-gray-800 rounded-lg w-full max-w-md">
            <summary className="cursor-pointer text-gray-300">جزئیات فنی</summary>
            <pre className="text-xs text-gray-400 mt-2 overflow-auto">{this.state.error?.toString()}</pre>
          </details>
          <button
            onClick={() => window.location.reload()}
            className="mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
          >
            Refresh صفحه
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
