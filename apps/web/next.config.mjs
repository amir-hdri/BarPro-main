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
      // Map tiles (CARTO voyager/dark + OSM fallback) are immutable raster
      // assets: serve stale-while-revalidate so pan/zoom never blocks on network
      // and sanction-related tile blips degrade gracefully.
      {
        urlPattern: ({ url }) =>
          url.hostname.endsWith("basemaps.cartocdn.com") ||
          url.hostname.endsWith("tile.openstreetmap.org"),
        handler: "StaleWhileRevalidate",
        options: {
          cacheName: "map-tiles",
          expiration: {
            maxEntries: 200,
            maxAgeSeconds: 7 * 24 * 60 * 60,
          },
          cacheableResponse: {
            statuses: [0, 200],
          },
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
