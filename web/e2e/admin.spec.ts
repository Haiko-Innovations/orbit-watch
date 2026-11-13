import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { type Browser, type Download, expect, type Page, test } from "@playwright/test";
import type { Hex } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { asParty, giveGasMoney, safeExecute, sendFrom, stackInfo, travelTo } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// The administrator view (phase 3, step 3.7), against the local stack. As on Base Sepolia, a
// timelock owns the reviewer registry and a 2-of-3 Safe proposes to it; here the Safe's
// signers are LOCAL TEST keys and the timelock waits a minute, not 48 hours. Everything is
// SIMULATED and has no value.

test.describe.configure({ mode: "serial" });

const REQUESTER = "requester:sim-cubesat-team";
// Someone who may execute a ready operation: any account with gas.
const ANYONE = localTestKey("e2e: anyone");

async function signedIn(browser: Browser, party: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await installTestWallet(page, localTestKey(party));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  return page;
}

async function adminPage(browser: Browser): Promise<Page> {
  const page = await signedIn(browser, stackInfo().admin.party);
  await page.getByRole("link", { name: "Administration" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Administration" })).toBeVisible();
  return page;
}

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

async function downloaded<T>(page: Page, click: () => Promise<void>): Promise<T> {
  const waiting: Promise<Download> = page.waitForEvent("download");
  await click();
  const file = await (await waiting).path();
  return JSON.parse(readFileSync(file, "utf8")) as T;
}

interface Batch {
  version: string;
  chainId: string;
  meta: { name: string; checksum: string; createdFromSafeAddress: string };
  transactions: { to: Hex; value: string; data: Hex }[];
}

interface Operation {
  operation_id: string;
  state: string;
  ready_at: string;
}

async function operations(page: Page): Promise<Operation[]> {
  return (await asParty(page.request, "admin", "GET", "/v1/admin/governance")).json
    .operations as Operation[];
}

async function reviewers(page: Page): Promise<string[]> {
  const view = await asParty(page.request, "admin", "GET", "/v1/admin/governance");
  return (view.json.registry as { reviewers: { address: string }[] }).reviewers.map(
    (r) => r.address,
  );
}

test("the administrator sees requests, payments, errors and events, and runs tick", async ({
  browser,
}) => {
  const page = await adminPage(browser);
  await expect(page.getByRole("heading", { level: 2, name: "Requests" })).toBeVisible();
  const requests = page.getByRole("table", { name: "Requests" });
  const settled = requests.getByRole("row").filter({ hasText: "SIM-REQ-3000" });
  await expect(settled).toContainText("Settled");
  await expect(settled).toContainText("station:SIM-ESPOO: 1 TESTUSD (observer_reward)");
  const inReview = requests.getByRole("row").filter({ hasText: "SIM-REQ-3006" });
  await expect(inReview).toContainText("Challenged; reviewers are checking it");
  await expect(page.getByText(/^7 requests: /)).toBeVisible();
  await expect(page.getByText("No conflicts and no failed transactions.")).toBeVisible();
  const log = page.getByRole("table", { name: "Event log" });
  await expect(log).toContainText("Settled");
  await expect(log).toContainText("Challenged");
  await audit(page);

  await page.getByRole("button", { name: "Run tick" }).click();
  await expect(
    page.getByText(/^Done: \d+ requests? changed, \d+ transactions? sent\.$/),
  ).toBeVisible();
});

test("the simulator and the demo datasets make SIMULATED files to download", async ({
  browser,
}) => {
  const page = await adminPage(browser);
  const simulator = page.getByRole("form", { name: "Simulator" });
  await expect(simulator.getByLabel("Instrument")).toHaveValue("sim-cmos-gps");
  await simulator.getByLabel("Target").selectOption("339001");
  await simulator.getByLabel("Passes at most").fill("1");
  await expect(simulator.getByLabel("Passes at most")).toHaveValue("1");
  await simulator.getByRole("button", { name: "Simulate" }).click();
  await expect(simulator).toContainText(/\d+ SIMULATED observations\./);
  const simulated = await downloaded<{ source: { notes: string } }>(page, () =>
    simulator.getByRole("link", { name: /^Download simulated-sim-cmos-gps-/ }).click(),
  );
  expect(simulated.source.notes).toContain("SIMULATED");

  const demo = page.getByRole("region", { name: "Demo datasets" });
  await demo.getByRole("button", { name: "Make wrong_target" }).click();
  await expect(demo.getByRole("status")).toContainText("Expected: fail (orbit_residuals)");
  const wrong = await downloaded<{ source: { notes: string } }>(page, () =>
    demo.getByRole("link", { name: "Download demo-wrong_target.json" }).click(),
  );
  expect(wrong.source.notes).toContain("SIM-CUBESAT-B");
});

test("a reviewer is added through the Safe and the timelock, then removed again", async ({
  browser,
}) => {
  const { governance } = stackInfo();
  const newcomer = privateKeyToAccount(localTestKey("reviewer:sim-e2e-newcomer")).address;
  await giveGasMoney(privateKeyToAccount(ANYONE).address);
  const page = await adminPage(browser);
  const details = page.locator("dl.details").filter({ hasText: "Timelock delay" });
  await expect(details).toContainText("1 minute");
  await expect(details).toContainText("2 of 3 owners sign");
  await expect(details).toContainText("The Safe may propose to the timelock.");
  await expect(details).toContainText(governance.safe);
  expect(await reviewers(page)).not.toContain(newcomer);

  // The administrator prepares the change; the page sends nothing.
  await page.getByLabel("Add a reviewer").check();
  await page.getByLabel("Reviewer: wallet address or party name").fill(newcomer);
  await page.getByRole("button", { name: "Prepare the Safe transaction" }).click();
  const prepared = page.getByRole("status").filter({ hasText: "Prepared:" });
  await expect(prepared).toContainText(`Prepared: addReviewer(${newcomer})`);
  await audit(page);
  const batch = await downloaded<Batch>(page, () =>
    prepared.getByRole("link", { name: "Download the batch file" }).click(),
  );
  expect(batch.version).toBe("1.0");
  expect(batch.chainId).toBe("31337");
  expect(batch.meta.checksum).toMatch(/^0x[0-9a-f]{64}$/);
  expect(batch.meta.createdFromSafeAddress).toBe(governance.safe);
  const [schedule] = batch.transactions;
  if (!schedule) throw new Error("the batch file has no transaction");
  expect(schedule.to).toBe(governance.timelock);

  // The Safe's owners schedule it, with the file's own data.
  await safeExecute(schedule.to, schedule.data);
  await page.getByRole("button", { name: "Refresh" }).click();
  const operation = page
    .getByRole("listitem")
    .filter({ hasText: `registry.addReviewer(${newcomer})` });
  await expect(operation).toContainText("Waiting");

  // After the delay anyone executes it, with the page's execute file.
  const [scheduled] = await operations(page);
  if (!scheduled) throw new Error("no operation");
  await travelTo(scheduled.ready_at);
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(operation).toContainText("Ready: anyone may execute it");
  await operation.getByText("Execute", { exact: true }).click();
  const execute = await downloaded<Batch>(page, () =>
    operation.getByRole("link", { name: "Download the execute file" }).click(),
  );
  const [call] = execute.transactions;
  if (!call) throw new Error("the execute file has no transaction");
  await sendFrom(ANYONE, call.to, call.data);
  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(operation).toContainText("Done");
  await expect(page.getByRole("listitem").filter({ hasText: newcomer }).first()).toContainText(
    "no party here",
  );
  expect(await reviewers(page)).toContain(newcomer);

  // Removed again the same way (through the API), so that later rounds draw as before.
  const removal = (
    await asParty(page.request, "admin", "POST", "/v1/admin/governance/proposals", {
      action: "remove",
      reviewer: newcomer,
    })
  ).json.proposal as {
    operation_id: string;
    schedule: Batch["transactions"][0];
    execute: Batch["transactions"][0];
  };
  await safeExecute(removal.schedule.to, removal.schedule.data);
  const waiting = (await operations(page)).find((o) => o.operation_id === removal.operation_id);
  if (!waiting) throw new Error("the removal was not scheduled");
  await travelTo(waiting.ready_at);
  await sendFrom(ANYONE, removal.execute.to, removal.execute.data);
  expect(await reviewers(page)).not.toContain(newcomer);
});

test("the view can do nothing the API refuses", async ({ browser }) => {
  // The administrator's own mistakes come back as the API's refusals.
  const admin = await adminPage(browser);
  const existing = stackInfo().parties["reviewer:sim-aino"]?.address ?? "";
  await admin.getByLabel("Add a reviewer").check();
  await admin.getByLabel("Reviewer: wallet address or party name").fill(existing);
  await admin.getByRole("button", { name: "Prepare the Safe transaction" }).click();
  await expect(admin.getByRole("alert")).toContainText("is already a reviewer");

  // Anyone else signed in sees no administration, and the API refuses its session.
  const page = await signedIn(browser, REQUESTER);
  await expect(page.getByRole("link", { name: "Administration" })).toHaveCount(0);
  await page.goto("/#/admin");
  await expect(page.getByText("This page is for administrators.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Run tick" })).toHaveCount(0);
  const origin = new URL(page.url()).origin;
  for (const path of ["/v1/admin/overview", "/v1/admin/governance", "/v1/admin/demo-datasets"]) {
    const refused = await page.request.get(path);
    expect(refused.status(), path).toBe(403);
  }
  for (const path of ["/v1/admin/tick", "/v1/admin/simulate", "/v1/admin/governance/proposals"]) {
    const refused = await page.request.post(path, {
      headers: { Origin: origin, "Idempotency-Key": `e2e-refused-${path}` },
      data: {},
    });
    expect(refused.status(), path).toBe(403);
  }
  // Without signing in, nothing at all.
  const anonymous = await (await browser.newContext()).newPage();
  expect((await anonymous.request.get("/v1/admin/overview")).status()).toBe(401);
});
