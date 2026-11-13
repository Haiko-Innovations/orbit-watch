import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { freshObservations } from "./stack";

// The public pages, against the local stack (phase 3, steps 3.1 and 3.7). Everything is
// LOCAL and SIMULATED, on a chain of no value. None of them needs signing in.

const pages = [
  { path: "/#/", heading: "Network" },
  { path: "/#/requests", heading: "Open requests" },
  { path: "/#/attestations", heading: "Attestations" },
  { path: "/#/quality", heading: "Station quality meter" },
  { path: "/#/nowhere", heading: "Page not found" },
];

for (const { path, heading } of pages) {
  test(`${heading}: testnet label and no accessibility violations`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
    const label = page.getByTestId("testnet-label");
    await expect(label).toContainText("local Anvil test chain, no real value");
    await expect(label).toContainText("SIMULATED");
    for (const colorScheme of ["light", "dark"] as const) {
      await page.emulateMedia({ colorScheme });
      const audit = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
        .analyze();
      expect(audit.violations, `${colorScheme} colours`).toEqual([]);
    }
    // No sideways scrolling on a phone.
    await page.setViewportSize({ width: 360, height: 800 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      360,
    );
  });
}

test("the network page shows the local chain and its contracts", async ({ page }) => {
  await page.goto("/");
  const details = page.locator("dl.details");
  await expect(details).toContainText("local Anvil chain");
  await expect(details).toContainText("31337");
  await expect(details).toContainText("TESTUSD");
  await expect(details).toContainText("none (local chain)");
  await expect(page.getByRole("contentinfo")).toContainText("0.4.0.dev0");
});

test("open requests list the funded and the unfunded SIMULATED requests", async ({ page }) => {
  await page.goto("/#/requests");
  // Other tests reserve some of the stack's requests; these two stay open.
  const funded = page.getByRole("article", { name: /after deployment/ });
  await expect(funded).toContainText("SIMULATED");
  await expect(funded).toContainText("SIM-REQ-3001");
  await expect(funded).toContainText("Funded, open for observers");
  await expect(funded).toContainText("1 TESTUSD");
  await expect(funded).toContainText("0.1 TESTUSD");
  await expect(funded).toContainText("2026-11-01 15:00 UTC");
  await expect(funded).toContainText("2026-11-03 12:00 UTC");

  const unfunded = page.getByRole("article", { name: /not funded yet/ });
  await expect(unfunded).toContainText("Published, waiting for funding");
});

test("the keyboard moves between pages and focus follows", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Network" })).toBeVisible();
  const link = page.getByRole("link", { name: "Open requests" });
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/#\/requests$/);
  await expect(page.getByRole("heading", { level: 1, name: "Open requests" })).toBeFocused();
  await expect(link).toHaveAttribute("aria-current", "page");
});

test("the app runs under the service's content security policy", async ({ page }) => {
  const problems: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") problems.push(message.text());
  });
  page.on("pageerror", (error) => problems.push(error.message));
  const response = await page.goto("/");
  expect(response?.headers()["content-security-policy"]).toContain("script-src 'self'");
  await expect(page.getByRole("heading", { level: 1, name: "Network" })).toBeVisible();
  await page.goto("/#/requests");
  await expect(page.getByRole("article").first()).toBeVisible();
  expect(problems).toEqual([]);
});

test("the attestation browser lists the automated results without signing in", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Attestations" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Attestations" })).toBeVisible();
  const settled = page.getByRole("row").filter({ hasText: "SIM-REQ-3000" });
  await expect(settled).toContainText("Automated result");
  await expect(settled).toContainText("verdict pass");
  await expect(settled).toContainText("the service (verifier key)");
  await expect(page.getByRole("row").filter({ hasText: "SIM-REQ-3006" })).toContainText(
    "verdict pass",
  );
  // A local chain has no EAS Scan; on Base Sepolia each UID links there.
  await expect(page.getByText("There is no EAS Scan for a local chain")).toBeVisible();
  await expect(page.getByRole("link", { name: /^0x/ })).toHaveCount(0);
  await expect(page.locator("dl.details")).toContainText(
    "0x4200000000000000000000000000000000000021",
  );
});

test("the quality meter scores an observation file without signing in", async ({ page }) => {
  await page.goto("/#/quality");
  await page.getByLabel("Observation file").setInputFiles({
    name: "station-SIM-ESPOO.json",
    mimeType: "application/json",
    buffer: freshObservations("station:SIM-ESPOO", 0),
  });
  await page.getByRole("button", { name: "Measure" }).click();
  const report = page.getByRole("region", { name: /^Station: / });
  await expect(report.getByRole("heading", { level: 2 })).toContainText("SIMULATED");
  await expect(report).toContainText("All observations");
  await expect(report).toContainText("SIM-CUBESAT-A");
  await expect(report).toContainText("Residuals include the error of the public reference orbit");

  await page.getByLabel("Observation file").setInputFiles({
    name: "broken.json",
    mimeType: "application/json",
    buffer: Buffer.from("{ not json"),
  });
  await page.getByRole("button", { name: "Measure" }).click();
  await expect(page.getByRole("alert")).toContainText("cannot read the observations");
});
