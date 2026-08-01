import type { NextConfig } from "next";
import { realpathSync } from "node:fs";
import path from "node:path";
import bundleAnalyzer from "@next/bundle-analyzer";

// v0.7.127 — opt-in bundle-size visualization. Run `npm run build:analyze`
// to get HTML reports of every chunk + which modules contributed to it.
// Output: .next/analyze/{client.html, server.html, edge.html}. Useful
// for identifying lazy-load candidates and accidentally-bundled deps
// (e.g. a server-only library leaking into the client bundle).
const withBundleAnalyzer = bundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
  openAnalyzer: false,
});

export function resolveTurbopackRoot(
  frontendDir: string,
  resolveRealPath: (path: string) => string = realpathSync,
) {
  try {
    const nodeModulesTarget = resolveRealPath(path.join(frontendDir, "node_modules"));
    return path.dirname(path.dirname(nodeModulesTarget));
  } catch {
    return path.dirname(frontendDir);
  }
}

const nextConfig: NextConfig = {
  // Resolve from the actual dependency target so both a normal checkout and a
  // worktree with shared dependencies stay within Turbopack's filesystem root.
  turbopack: {
    root: resolveTurbopackRoot(__dirname),
  },

  // Enable standalone output for optimized Docker deployment
  output: "standalone",

  // Experimental features
  // Type assertion needed: proxyClientMaxBodySize is valid in Next.js 15 but types lag behind
  experimental: {
    // Keep browser uploads aligned with the backend source cap
    // (DEEPER_NOTEBOOK_SOURCE_UPLOAD_MAX_BYTES defaults to 500 MB). A lower Next proxy
    // cap rejects large-but-valid PDFs before FastAPI can stream, clean up,
    // and return the app's friendly 413 response.
    proxyClientMaxBodySize: '500mb',
  } as NextConfig['experimental'],

  // API Rewrites: Proxy /api/* requests to FastAPI backend
  // This simplifies reverse proxy configuration - users only need to proxy to port 8502
  // Next.js handles internal routing to the API backend on port 5055
  async rewrites() {
    // INTERNAL_API_URL: Where Next.js server-side should proxy API requests
    // Default: http://localhost:5055 (single-container deployment)
    // Override for multi-container: INTERNAL_API_URL=http://api-service:5055
    const internalApiUrl = process.env.INTERNAL_API_URL || 'http://localhost:5055'

    console.log(`[Next.js Rewrites] Proxying /api/* to ${internalApiUrl}/api/*`)

    return [
      {
        source: '/api/:path*',
        destination: `${internalApiUrl}/api/:path*`,
      },
    ]
  },
};

export default withBundleAnalyzer(nextConfig);
