import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  use: { baseURL: "http://localhost:3000", trace: "on-first-retry" },
  timeout: 30_000,
});
