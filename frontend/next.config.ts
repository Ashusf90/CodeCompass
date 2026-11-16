import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    const backend = process.env.RENDER_BACKEND_URL;

    if (!backend) return [];

    return [
      {
        source: "/api/:path*",
        destination: `${backend.endsWith("/") ? backend.slice(0, -1) : backend}/api/:path*`,
      },
    ];
  },
  output: "standalone",
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    root: process.cwd(),
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
