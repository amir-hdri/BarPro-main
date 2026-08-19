import path from "node:path";
import { fileURLToPath } from "node:url";

import withPWAInit from "@ducanh2912/next-pwa";

const withPWA = withPWAInit({
  dest: "public",
  cacheOnFrontEndNav: true,
  disable: process.env.NODE_ENV === "development",
  registerInDev: false,
  dynamicStartUrl: true,
  buildExcludes: [/middleware-manifest\.json$/],
  scope: "/",
  sw: "service-worker.js",
  reloadOnOnline: true,
  extendDefaultRuntimeCaching: true,
  workboxOptions: {
    skipWaiting: true,
    clientsClaim: true,
    runtimeCaching: [
      {
        urlPattern: ({ url }) => url.pathname.startsWith("/api/"),
        handler: "NetworkOnly",
        options: {
          cacheName: "apis",
        },
      },
    ],
  },
});

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  outputFileTracingRoot: process.cwd(),
  images: {
    remotePatterns: [],
  },
  async rewrites() {
    const backendUrl = process.env.INTERNAL_BACKEND_URL || "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
      {
        source: "/readyz",
        destination: `${backendUrl}/readyz`,
      },
      {
        source: "/browser-pool/:path*",
        destination: `${backendUrl}/browser-pool/:path*`,
      },
      {
        source: "/workers/:path*",
        destination: `${backendUrl}/workers/:path*`,
      },
      {
        source: "/proxies/:path*",
        destination: `${backendUrl}/proxies/:path*`,
      },
      {
        source: "/captcha/:path*",
        destination: `${backendUrl}/captcha/:path*`,
      },
      {
        source: "/circuit-breaker/:path*",
        destination: `${backendUrl}/circuit-breaker/:path*`,
      },
    ];
  },
};

export default withPWA(nextConfig);
