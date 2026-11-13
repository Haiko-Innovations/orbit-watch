import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { installTestWallet, localTestKey } from "./testWallet";

// Transactions in the browser (phase 3, step 3.3), against the local stack. The stack seeds
// SIM-REQ-3000, settled: the escrow owes station:SIM-ESPOO and the requester some credit
// (other tests may add to it). The tests run in order and spend it. LOCAL TEST keys, no value.

test.describe.configure({ mode: "serial" });

async function signIn(page: Page) {
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
}

async function startWithdrawal(page: Page) {
  await page.getByRole("button", { name: /^Withdraw \d/ }).click();
  const flow = page.getByRole("region", { name: "Check and send" });
  await expect(flow).toContainText("Withdraw your credit");
  await expect(flow).toContainText("Orbit Watch escrow");
  await expect(flow).toContainText("withdraw");
  return flow;
}

test("declining in the wallet sends nothing", async ({ page }) => {
  await installTestWallet(page, localTestKey("station:SIM-ESPOO"), { declineSend: true });
  await signIn(page);
  await expect(page.locator("dl.details").nth(1)).toContainText("TESTUSD");
  const flow = await startWithdrawal(page);
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const audit = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(audit.violations, `${colorScheme} colours`).toEqual([]);
  }
  await flow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(flow.getByRole("alert")).toContainText(
    "You declined in your wallet. Nothing was sent.",
  );
  await flow.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("button", { name: /^Withdraw \d/ })).toBeVisible();
});

test("a wallet on another network sends nothing", async ({ page }) => {
  await installTestWallet(page, localTestKey("station:SIM-ESPOO"), { refuseSwitch: true });
  await signIn(page);
  // The user moves the wallet to another network after signing in.
  await page.evaluate(() =>
    (
      window as unknown as { orbitWatchTestWalletChain: (id: number) => void }
    ).orbitWatchTestWalletChain(1),
  );
  const flow = await startWithdrawal(page);
  await flow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(flow.getByRole("alert")).toContainText(
    "Your wallet is on another network and did not switch to Foundry",
  );
  await flow.getByRole("button", { name: "Cancel" }).click();
  await expect(page.getByRole("button", { name: /^Withdraw \d/ })).toBeVisible();
});

test("a station withdraws its credit with its own wallet", async ({ page }) => {
  await installTestWallet(page, localTestKey("station:SIM-ESPOO"));
  await signIn(page);
  const flow = await startWithdrawal(page);
  await flow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(flow).toContainText("Done. The chain confirmed every transaction.");
  await expect(flow.locator(".tx-confirmed")).toContainText("Confirmed");
  await flow.getByRole("button", { name: "Close" }).click();

  const balance = page.locator("dl.details").nth(1);
  await expect(balance).toContainText("Waiting for you in the escrow0 TESTUSD");
  await expect(page.getByText("Nothing to withdraw.")).toBeVisible();
  const row = page.getByRole("row", { name: /withdraw/ });
  await expect(row).toContainText("Confirmed");
});

test("two tabs, one credit: the chain refuses the second withdrawal and the page says why", async ({
  context,
}) => {
  const key = localTestKey("requester:sim-cubesat-team");
  const first = await context.newPage();
  await installTestWallet(first, key);
  await signIn(first);
  const second = await context.newPage();
  await installTestWallet(second, key);
  await second.goto("/#/account"); // signed in already: the tabs share the session cookie
  await expect(second.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();

  const firstFlow = await startWithdrawal(first);
  const secondFlow = await startWithdrawal(second);
  await firstFlow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(firstFlow).toContainText("Done. The chain confirmed every transaction.");

  // The second tab was reloaded, so it asks which wallet to send with.
  await secondFlow.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(secondFlow.getByRole("alert")).toContainText(
    "there is nothing to withdraw any more. It was probably withdrawn already",
  );
});
