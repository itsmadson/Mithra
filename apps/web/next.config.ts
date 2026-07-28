import createNextIntlPlugin from "next-intl/plugin";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default createNextIntlPlugin("./src/i18n.ts")(nextConfig);
