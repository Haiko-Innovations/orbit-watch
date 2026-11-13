import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

// The public pages, against the local stack (phase 3, step 3.1). Everything is LOCAL and
// SIMULATED, on a chain of no value.

const pages = [
  { path: "/#/", heading: "Network" },
  { path: "/#/requests", heading: "Open requests" },
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
  await expect(page.getByRole("article")).toHaveCount(3);

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
  await expect(page.getByRole("article")).toHaveCount(3);
  expect(problems).toEqual([]);
});
