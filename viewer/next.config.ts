import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Plain static files: the browser talks to Supabase directly, and nothing runs on a server.
  output: "export",
};

export default nextConfig;
