/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // typecheck runs in CI (tsc); don't fail the production build on lint nits
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
