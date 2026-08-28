import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Build straight into the folder GitHub Actions deploys.
  build: {
    outDir: "../web",
    emptyOutDir: true,
  },
});
