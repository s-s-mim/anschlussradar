import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs locally with `func start` on port 7071.
// In production VITE_API_BASE points at the API Function App (set in the deploy workflow).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:7071" },
  },
  build: {
    target: "es2020",
    sourcemap: false,
  },
});
