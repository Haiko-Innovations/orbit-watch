import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the local stack (decision P3-08): a LOCAL Anvil chain, the
// contracts, the service and SIMULATED parties, serving the built app on the API's origin.
// Build first (npm run build); the contracts must be built too (cd contracts && forge build).
const port = 8790;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: true,
  workers: 1,
  reporter: "list",
  use: { baseURL: `http://127.0.0.1:${port}`, trace: "retain-on-failure" },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `uv run --locked python tests/local_stack.py --port ${port} --chain-port 0 --web ../web/dist`,
    cwd: "../core",
    // The stack says "Ready." once its SIMULATED requests are in place.
    url: `http://127.0.0.1:${port}/v1/health`,
    wait: { stdout: /Ready\./ },
    timeout: 180_000,
    reuseExistingServer: false,
    stdout: "pipe",
    gracefulShutdown: { signal: "SIGTERM", timeout: 15_000 },
  },
});
