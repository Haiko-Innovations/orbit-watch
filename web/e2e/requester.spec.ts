import { readFileSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "@playwright/test";
import { asParty, freshObservations, signAndReport, travelTo } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// The requester's view (phase 3, step 3.4), against the local stack. The station's part,
// whose view comes in step 3.5, is played through the API with its LOCAL TEST key. The
// observations are fresh SIMULATED good ones from the stack. No real value anywhere.

test.describe.configure({ mode: "serial" });

const REQUESTER = "requester:sim-cubesat-team";

async function signIn(page: Page) {
  await installTestWallet(page, localTestKey(REQUESTER));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
}

async function audit(page: Page) {
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(result.violations, `${colorScheme} colours`).toEqual([]);
  }
}

/** A station reserves and delivers the good dataset, signing with its own key. */
async function stationDelivers(page: Page, station: string, id: string, dataset: number) {
  const reserved = await asParty(page.request, station, "POST", `/v1/requests/${id}/reserve`);
  expect(reserved.status, JSON.stringify(reserved.json)).toBe(202);
  await signAndReport(page.request, station, reserved.json as never);
  const delivered = await asParty(
    page.request,
    station,
    "POST",
    `/v1/requests/${id}/deliveries`,
    freshObservations(station, dataset),
    {
      format: "json",
    },
  );
  expect(delivered.status, JSON.stringify(delivered.json)).toBe(202);
  await signAndReport(page.request, station, delivered.json as never);
}

test("a requester creates, funds and follows a request to its report", async ({ page }) => {
  const id = "SIM-REQ-3101";
  await signIn(page);
  await page.getByRole("link", { name: "Your requests" }).click();
  await page.getByRole("link", { name: "New request" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "New request" })).toBeVisible();
  await audit(page);

  await page.getByLabel("Request ID").fill(id);
  await page.getByLabel("Title").fill("SIMULATED: track SIM-CUBESAT-A from the browser");
  await expect(page.getByLabel("Target")).toHaveValue("339001");
  await page.getByLabel("Observation window starts (UTC)").fill("2026-11-01T15:00");
  await page.getByLabel("Observation window ends (UTC)").fill("2026-11-02T03:00");
  await page.getByLabel("Delivery deadline (UTC)").fill("2026-11-03T12:00");
  await page.getByLabel("Challenge period (hours)").fill("1");
  await page.getByRole("button", { name: "Create draft" }).click();

  await expect(
    page.getByRole("heading", { level: 1, name: /track SIM-CUBESAT-A from the browser/ }),
  ).toBeVisible();
  await expect(page.locator(".status-line")).toContainText("Draft: only you see it");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.locator(".status-line")).toContainText("Published, waiting for funding");

  // The split and the deposit before anything is signed.
  await expect(page.getByText("Deposit: 1.3 TESTUSD")).toBeVisible();
  await expect(page.getByText("0.3 TESTUSD reserved for a reviewer round")).toBeVisible();
  await audit(page);
  await page.getByRole("button", { name: "Prepare the deposit" }).click();
  const flow = page.getByRole("region", { name: "Check and send" });
  await expect(flow).toContainText("Allow the escrow to take 1.3 TESTUSD");
  await expect(flow).toContainText(`Deposit 1.3 TESTUSD for ${id}`);
  await flow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(flow).toContainText("Done. The chain confirmed every transaction.");
  await flow.getByRole("button", { name: "Close" }).click();
  await expect(page.locator(".status-line")).toContainText("Funded, waiting for an observer");

  await stationDelivers(page, "station:SIM-ESPOO", id, 0);
  await page.reload();
  await expect(page.locator(".status-line")).toContainText("the challenge period is running");
  await expect(page.getByText("Automated verification: pass")).toBeVisible();
  await expect(page.getByRole("button", { name: "Prepare the challenge" })).toBeDisabled();

  // Nobody challenges: past the deadline the service settles it.
  const view = await asParty(page.request, REQUESTER, "GET", `/v1/requests/${id}`);
  const deadline = (view.json.record as { challenge_deadline: string }).challenge_deadline;
  await travelTo(new Date(new Date(deadline).getTime() + 60_000).toISOString());
  expect((await asParty(page.request, "admin", "POST", "/v1/admin/tick")).status).toBe(200);
  await page.reload();
  await expect(page.locator(".status-line")).toContainText("Settled · Outcome: accepted");
  await expect(page.getByText("station:SIM-ESPOO: 1 TESTUSD (observer reward)")).toBeVisible();
  await expect(page.getByText(`${REQUESTER}: 0.3 TESTUSD (back to the requester)`)).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Verification report" }).click(),
  ]);
  expect(download.suggestedFilename()).toBe(`${id}-report.json`);
  const report = JSON.parse(readFileSync(await download.path(), "utf8")) as { verdict: string };
  expect(report.verdict).toBe("pass");
});

test("a requester challenges a delivered result, and the escrow picks reviewers", async ({
  page,
}) => {
  const id = "SIM-REQ-3002"; // funded by the stack
  await signIn(page);
  await stationDelivers(page, "station:SIM-ESPOO", id, 1);
  await page.goto(`/#/requests/${id}`);
  await expect(page.locator(".status-line")).toContainText("the challenge period is running");
  await page.getByLabel("Reason").fill("SIMULATED: the track looks like the neighbouring object.");
  await page.getByRole("button", { name: "Prepare the challenge" }).click();
  const flow = page.getByRole("region", { name: "Check and send" });
  await expect(flow).toContainText(`Challenge the result of ${id}`);
  await flow.getByRole("button", { name: "Send with your wallet" }).click();
  await expect(flow).toContainText("Done. The chain confirmed every transaction.");
  await flow.getByRole("button", { name: "Close" }).click();
  await expect(page.locator(".status-line")).toContainText("Challenged; reviewers are checking it");
  await expect(page.getByText(/Reviewers chosen by the escrow: reviewer:sim-/)).toBeVisible();
});

test("someone else sees the terms but not the files, and cannot act", async ({ page }) => {
  await installTestWallet(page, localTestKey("station:SIM-TAMPERE"));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  // SIM-REQ-3002 is in review, so unpublished; a settled one is public to everyone.
  await page.goto("/#/requests/SIM-REQ-3002");
  await expect(page.getByRole("heading", { level: 1, name: "SIM-REQ-3002" })).toBeVisible();
  await expect(page.getByText("You are not a party of this request")).toBeVisible();
  await expect(page.getByRole("link", { name: "Verification report" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Publish" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Prepare the challenge" })).toHaveCount(0);
});
