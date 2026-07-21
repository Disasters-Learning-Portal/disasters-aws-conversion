import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Static SPA. Data is fetched at runtime from public raw-GitHub URLs (see src/data.ts),
// with a bundled snapshot in public/data/ as fallback. No backend, no env vars.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
  },
});
