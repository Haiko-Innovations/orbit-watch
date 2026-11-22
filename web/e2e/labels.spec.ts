import { type Browser, expect, type Page, test } from "@playwright/test";
import { asParty, stackInfo } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// Labels by source on every page that shows objects, reference orbits or observations
// (phase 5, step 5.5; decisions P5-09, D-52). The stack's data is all SIMULATED, so every
// label says so here; real objects and replays in the stack are the next pull request.
// It only reads.

const REQUESTER = "requester:sim-cubesat-team";
const STATION = "station:SIM-ESPOO";
const OWN_OBJECT = "a SIMULATED object of the service's own catalogue";
const OWN_ORBIT = "the service's own catalogue, epoch 2026-11-01 00:00 UTC";

async function signedIn(browser: Browser, party: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await installTestWallet(page, localTestKey(party));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  return page;
}

test("open requests say what each part of a request is", async ({ page }) => {
  await page.goto("/#/requests");
  const funded = page.getByRole("article", { name: /after deployment/ });
  await expect(funded.getByTestId("label-tags")).toHaveText("SIMULATED");
  const labels = funded.getByTestId("labels");
  await expect(labels).toContainText(OWN_OBJECT);
  await expect(labels).toContainText(OWN_ORBIT);
  await expect(labels).toContainText("SIMULATED observations, not delivered yet");
  await expect(labels).not.toContainText("real object");
});

test("a settled request names its observations and the orbit its report used", async ({
  browser,
}) => {
  const page = await signedIn(browser, STATION);
  await page.goto("/#/requests/SIM-REQ-3000");
  const labels = page.getByTestId("labels");
  await expect(labels.getByRole("heading", { name: "What this is" })).toBeVisible();
  await expect(labels).toContainText(OWN_OBJECT);
  await expect(labels).toContainText(OWN_ORBIT);
  await expect(labels).not.toContainText("the nearest so far");
  await expect(labels).toContainText(`SIMULATED, delivered by ${STATION}`);
});

test("the lists of requests tag each one", async ({ browser }) => {
  const requester = await signedIn(browser, REQUESTER);
  await requester.goto("/#/my-requests");
  await expect(requester.getByTestId("label-tags").first()).toHaveText("SIMULATED");
  const station = await signedIn(browser, STATION);
  await station.goto("/#/my-observations");
  await expect(station.getByTestId("label-tags").first()).toHaveText("SIMULATED");
  const admin = await signedIn(browser, stackInfo().admin.party);
  await admin.goto("/#/admin");
  await expect(admin.getByTestId("label-tags").first()).toHaveText("SIMULATED");
});

test("a review task labels its files, without naming its request", async ({ browser }) => {
  const reviewer =
    (stackInfo() as unknown as { in_review: { reviewers: string[] } }).in_review.reviewers[0] ??
    "";
  const page = await signedIn(browser, reviewer);
  const tasks = (await asParty(page.request, reviewer, "GET", "/v1/tasks")).json.tasks as {
    task_id: string;
  }[];
  await page.goto(`/#/tasks/${tasks[0]?.task_id ?? "none"}`);
  const labels = page.getByTestId("labels");
  await expect(labels).toContainText(OWN_ORBIT);
  await expect(labels).toContainText("SIMULATED, as the file says");
});

test("a new request says that a SIMULATED object makes a SIMULATED request", async ({
  browser,
}) => {
  const page = await signedIn(browser, REQUESTER);
  await page.goto("/#/new-request");
  await expect(page.getByText("A SIMULATED object: the request is SIMULATED too.")).toBeVisible();
  await expect(page.getByLabel("SIMULATED observations")).toHaveCount(0);
});

test("the testnet label says that real and SIMULATED data run side by side", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("testnet-label")).toContainText(
    "SIMULATED and real data side by side",
  );
});
