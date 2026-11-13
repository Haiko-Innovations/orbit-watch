import { defineConfig, devices } from "@playwright/test";

// The phase 3 demo on Base Sepolia (step 3.8; web/demo/README.md). Not part of CI: it uses
// the testnet keys of decision D-24 and spends a little testnet ETH. TESTNET ONLY, no real
// value. The service starts afresh in $ORBIT_WATCH_DEMO_DIR (web/demo/serve.sh).
const port = Number(process.env.ORBIT_WATCH_DEMO_PORT ?? 8795);
const dir = process.env.ORBIT_WATCH_DEMO_DIR ?? "";
const viewport = { width: 1280, height: 800 };

export default defineConfig({
  testDir: "demo",
  testMatch: "*.demo.ts",
  forbidOnly: true,
  workers: 1,
  retries: 0,
  // Every step waits for Base Sepolia, a block every two seconds.
  timeout: 60 * 60_000,
  expect: { timeout: 180_000 },
  reporter: "list",
  outputDir: `${dir}/playwright`,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    viewport,
    actionTimeout: 180_000,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport } }],
  webServer: {
    command: "bash demo/serve.sh",
    url: `http://127.0.0.1:${port}/v1/health`,
    timeout: 600_000,
    reuseExistingServer: false,
    stdout: "pipe",
    gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
  },
});
