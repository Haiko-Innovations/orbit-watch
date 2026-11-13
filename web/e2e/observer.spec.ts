import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { generatePrivateKey } from "viem/accounts";
import { giveGasMoney } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// The observer's view (phase 3, step 3.5), against the local stack: SIM-REQ-3004 and
// SIM-REQ-3005 are funded for these tests. Stations sign with LOCAL TEST keys; every
// observation is SIMULATED; nothing has value.

test.describe.configure({ mode: "serial" });

const WRONG_TARGET = fileURLToPath(
  new URL("../../examples/simulated/datasets/wrong_target/observations.json", import.meta.url),
);

async function audit(page: Page) {
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(result.violations, `${colorScheme} colours`).toEqual([]);
  }
  await page.emulateMedia({ colorScheme: "light" });
}

async function sendAll(page: Page, expected: string) {
  const flow = page.getByRole("region", { name: "Check and send" });
  await expect(flow).toContainText(expected);
  await flow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(flow).toContainText("Done. The chain confirmed every transaction.");
  await flow.getByRole("button", { name: "Close" }).click();
}

async function reserve(page: Page, id: string) {
  await page.getByRole("link", { name: "Open requests" }).click();
  await page.getByRole("button", { name: `Reserve ${id}` }).click();
  await sendAll(page, `Reserve ${id}`);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/SIMULATED/);
  await expect(page.locator(".status-line")).toContainText("Reserved by an observer");
}

test("a new station registers its profile, simulates observations and they pass", async ({
  page,
}) => {
  const address = await installTestWallet(page, generatePrivateKey());
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await page.getByLabel("an observer: I run a station").check();
  await page.getByLabel("Name").fill("SIM-OBS-TEST");
  await page.getByRole("button", { name: "Sign up and sign in" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();

  await page.getByRole("link", { name: "Your station" }).click();
  await expect(page.getByText("You have not registered your station yet.")).toBeVisible();
  await audit(page);
  await page.getByLabel("Start from").selectOption("sim-cmos-gps");
  await page.getByLabel("Station name").fill("Simulated test station near Lahti");
  // Not at SIM-ESPOO's place: two stations at one spot would deliver near-identical
  // observations, which the service rightly refuses as resubmitted data.
  await page.getByLabel("Latitude (degrees, north positive)").fill("60.98");
  await page.getByLabel("Longitude (degrees, east positive)").fill("25.66");
  await page.getByLabel("Altitude (metres)").fill("100");
  await page.getByRole("button", { name: "Save the profile" }).click();
  await expect(page.getByRole("status")).toContainText("Saved.");
  await expect(page.locator("dl.details")).toContainText("SIM-OBS-TEST");

  // A new wallet has no ETH for fees yet: the page says so, and nothing is sent.
  await page.getByRole("link", { name: "Open requests" }).click();
  await page.getByRole("button", { name: "Reserve SIM-REQ-3004" }).click();
  const empty = page.getByRole("region", { name: "Check and send" });
  await empty.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(empty.getByRole("alert")).toContainText(
    "Your wallet has no ETH for the network fee",
  );
  await empty.getByRole("button", { name: "Cancel" }).click();
  await giveGasMoney(address); // as a faucet would

  await reserve(page, "SIM-REQ-3004");
  await page.getByRole("button", { name: "Simulate observations with your station" }).click();
  await expect(page.getByText("SIM-REQ-3004-SIM-OBS-TEST-simulated.json")).toBeVisible();
  const sha = (await page.getByTestId("delivery-sha256").textContent()) ?? "";
  expect(sha).toMatch(/^[0-9a-f]{64}$/);
  await audit(page);
  await page.getByRole("button", { name: "Prepare the delivery" }).click();
  const flow = page.getByRole("region", { name: "Check and send" });
  await expect(flow).toContainText(sha); // the call data carries the chosen file's SHA-256
  await sendAll(page, "Record your delivery for SIM-REQ-3004");

  await expect(page.locator(".status-line")).toContainText("the challenge period is running");
  await expect(page.getByText("Verdict: pass")).toBeVisible();
  await expect(page.locator(".check-pass").first()).toBeVisible();
  await expect(page.getByText("Target matches the request: passed")).toBeVisible();

  await page.getByRole("link", { name: "Your observations" }).click();
  await expect(page.getByRole("link", { name: /first manoeuvre/ })).toBeVisible();
});

test("a station delivers its own file, sees why it failed, and challenges", async ({ page }) => {
  await installTestWallet(page, localTestKey("station:SIM-ESPOO"));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();

  await reserve(page, "SIM-REQ-3005");
  await page.getByLabel("Observation file").setInputFiles(WRONG_TARGET);
  const expected = createHash("sha256").update(readFileSync(WRONG_TARGET)).digest("hex");
  await expect(page.getByTestId("delivery-sha256")).toHaveText(expected);
  await page.getByRole("button", { name: "Prepare the delivery" }).click();
  await sendAll(page, "Record your delivery for SIM-REQ-3005");

  await expect(page.getByText("Verdict: fail")).toBeVisible();
  await expect(page.locator(".check-fail").first()).toBeVisible();
  await expect(page.getByText("The automated verification rejected your delivery")).toBeVisible();
  await page.getByLabel("Reason").fill("SIMULATED: these are my observations of the target.");
  await page.getByRole("button", { name: "Prepare the challenge" }).click();
  await sendAll(page, "Challenge the result of SIM-REQ-3005");
  await expect(page.locator(".status-line")).toContainText("Challenged; reviewers are checking it");
});
