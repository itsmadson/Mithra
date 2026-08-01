import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The container image ships a server and the compiled app rather than a
  // node_modules tree.
  output: "standalone",
};

export default createNextIntlPlugin("./src/i18n.ts")(nextConfig);
