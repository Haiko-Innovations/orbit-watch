import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `npm run dev` sends API calls to a running service on port 8787: the local stack
// (core/tests/local_stack.py) or `orbit-watch serve --port 8787`. The built app is served
// by the service itself, on the API's own origin (decision D-25).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, strictPort: true, proxy: { "/v1": "http://127.0.0.1:8787" } },
  build: { outDir: "dist" },
  test: { include: ["src/**/*.test.ts"], environment: "node" },
});
