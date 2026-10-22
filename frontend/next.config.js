/** @type {import('next').NextConfig} */
const fs = require("node:fs");
const path = require("node:path");
const { nextTypeScriptConfig } = require('./scripts/next-typescript-config.cjs');
const distDir = process.env.NEXT_BUILD_DIR || '.next';
const publicKeys = ["NEXT_PUBLIC_API_URL", "NEXT_PUBLIC_WS_URL", "NEXT_PUBLIC_CAMPUS_LAT", "NEXT_PUBLIC_CAMPUS_LNG", "NEXT_PUBLIC_CAMPUS_ZOOM"];
const rootEnv = path.join(__dirname, "..", ".env");
if (fs.existsSync(rootEnv)) {
  for (const line of fs.readFileSync(rootEnv, "utf8").split(/\r?\n/)) {
    const match = line.match(/^([A-Z_]+)=(.*)$/);
    if (match && publicKeys.includes(match[1]) && process.env[match[1]] === undefined) {
      process.env[match[1]] = match[2].trim().replace(/^['"]|['"]$/g, "");
    }
  }
}
const nextConfig = {
  // Allow verification builds without changing the directory served by a running app.
  distDir,
  typescript: nextTypeScriptConfig(__dirname, distDir),
  // "standalone" restructures the build into a pruned server bundle meant to
  // be run via `node server.js` inside the Docker image (see Dockerfile) —
  // it is NOT compatible with `next start`/`next dev`, which is how this
  // project is actually run locally. Applying it unconditionally caused
  // "Cannot find module './xxx.js'" chunk errors on every native run.
  // Only the Docker build sets DOCKER_BUILD=true.
  output: process.env.DOCKER_BUILD === "true" ? "standalone" : undefined,
  reactStrictMode: true,
  images: {
    domains: ["localhost"],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
