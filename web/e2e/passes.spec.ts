import { expect, type Page, test } from "@playwright/test";
import { installTestWallet, localTestKey } from "./testWallet";

// A station's visible passes for a request (phase 5, step 5.7; decisions P5-12, D-58),
// against the local stack: SIM-ESPOO's profile is at its place to about a kilometre, and
// SIM-REQ-3001 is funded and open. Everything is LOCAL and SIMULATED. It only reads.

async function signIn(page: Page, party: string) {
  await installTestWallet(page, localTestKey(party));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
}

test("a station sees which passes of a request it can see", async ({ page }) => {
  await signIn(page, "station:SIM-ESPOO");
  await page.goto("/#/requests");
  const card = page.getByRole("article", { name: /after deployment/ });
  await card.getByRole("link", { name: "Your visible passes" }).click();
  await expect(page).toHaveURL(/#\/requests\/SIM-REQ-3001$/);
  const passes = page.getByTestId("passes");
  await expect(passes.getByRole("heading", { name: "Your visible passes" })).toBeVisible();
  await expect(passes).toContainText("elevation limit of 20°");
  await expect(passes).toContainText("at least 6° below the horizon");
  const visible = passes.locator("tr.visible-pass");
  await expect(visible).toHaveCount(2); // the two evening passes, lit under a dark sky
  await expect(visible.first()).toContainText("2026-11-01 15:");
  await expect(visible.first()).toContainText("highest");
  // Above SIM-ESPOO's limit of 20° the window has only these two passes.
  await expect(passes.locator("tbody tr")).toHaveCount(2);
  await expect(passes).not.toContainText("not visible");
});

test("a station without a profile is asked to register it", async ({ page }) => {
  await signIn(page, "station:SIM-OULU");
  await page.goto("/#/requests/SIM-REQ-3001");
  const passes = page.getByTestId("passes");
  await expect(passes).toContainText("Register your station to see its passes:");
  await expect(passes.getByRole("link", { name: "Your station" })).toBeVisible();
});

test("a requester sees no pass list", async ({ page }) => {
  await signIn(page, "requester:sim-cubesat-team");
  await page.goto("/#/requests/SIM-REQ-3001");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("SIMULATED");
  await expect(page.getByTestId("passes")).toHaveCount(0);
});
