import { type Browser, expect, type Page, test } from "@playwright/test";
import { asParty, stackInfo } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// Labels by source on every page that shows objects, reference orbits or observations
// (phase 5, step 5.5; decisions P5-09, D-52, D-53). The stack's own objects are SIMULATED;
// beside them it has a made-up stand-in for a real object (339990) with an uploaded orbit,
// a SIMULATED and a real request for it, and a replay of made-up published observations
// that settled. It only reads.

const REQUESTER = "requester:sim-cubesat-team";
const STATION = "station:SIM-ESPOO";
const REPLAY_STATION = "station:LOCAL-REPLAY";
const EXAMPLE_ORCID = "0000-0002-1825-0097";
const OWN_OBJECT = "a SIMULATED object of the service's own catalogue";
const OWN_ORBIT = "the service's own catalogue, epoch 2026-11-01 00:00 UTC";
const STAND_IN =
  "a real object, added by an administrator: LOCAL TEST: stands in for a real object";
const UPLOADED_ORBIT = "uploaded by an administrator, epoch 2026-11-01 00:00 UTC";

async function signedIn(browser: Browser, party: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await installTestWallet(page, localTestKey(party));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  return page;
}

test("open requests show a real object and a SIMULATED one side by side", async ({ page }) => {
  await page.goto("/#/requests");
  const simulated = page.getByRole("article", { name: /after deployment/ });
  await expect(simulated.getByTestId("label-tags")).toHaveText("SIMULATED");
  const own = simulated.getByTestId("labels");
  await expect(own).toContainText(OWN_OBJECT);
  await expect(own).toContainText(OWN_ORBIT);
  await expect(own).toContainText("SIMULATED observations, not delivered yet");
  await expect(own).not.toContainText("real object");

  const real = page.getByRole("article", { name: /Real observations of the stand-in/ });
  await expect(real.getByTestId("label-tags")).toHaveText("Real object");
  const labels = real.getByTestId("labels");
  await expect(labels).toContainText(STAND_IN);
  await expect(labels).toContainText(`${UPLOADED_ORBIT} (the nearest so far`);
  await expect(labels).toContainText("real observations, not delivered yet");
  await expect(labels.locator(".badge")).toHaveCount(0); // nothing here is SIMULATED
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

test("simulated stations observe a real object: only the observations are SIMULATED", async ({
  browser,
}) => {
  const page = await signedIn(browser, STATION);
  await page.goto("/#/requests/SIM-REQ-3010");
  await expect(page.getByText("Verified; the challenge period is running")).toBeVisible();
  const labels = page.getByTestId("labels");
  await expect(labels).toContainText(STAND_IN);
  await expect(labels).toContainText(UPLOADED_ORBIT);
  await expect(labels).not.toContainText("the nearest so far");
  await expect(labels).toContainText(`SIMULATED, delivered by ${STATION}`);
  await expect(labels.locator(".badge")).toHaveCount(1); // on the observations only
});

test("a replay settles and names its source, licence and observers", async ({ browser }) => {
  const page = await signedIn(browser, REQUESTER);
  await page.goto("/#/requests/REPLAY-3020");
  await expect(page.getByText("Settled", { exact: true })).toBeVisible();
  const labels = page.getByTestId("labels");
  await expect(labels).toContainText(STAND_IN);
  await expect(labels).toContainText(UPLOADED_ORBIT);
  await expect(labels).toContainText(
    "replayed: published in A MADE-UP SOURCE, for the local stack under CC-BY-4.0 by",
  );
  await expect(labels.getByRole("link", { name: EXAMPLE_ORCID })).toHaveAttribute(
    "href",
    `https://orcid.org/${EXAMPLE_ORCID}`,
  );
  await expect(labels).toContainText(
    `delivered by the replay station ${REPLAY_STATION}, which is not their observer`,
  );
  await expect(labels.locator(".badge")).toHaveCount(0);
});

test("the lists of requests tag each one", async ({ browser }) => {
  const tags = (page: Page, id: string) =>
    page.getByRole("listitem").filter({ hasText: id }).getByTestId("label-tags");
  const requester = await signedIn(browser, REQUESTER);
  await requester.goto("/#/my-requests");
  await expect(tags(requester, "SIM-REQ-3001")).toHaveText("SIMULATED");
  await expect(tags(requester, "SIM-REQ-3010")).toHaveText("SIMULATEDReal object");
  await expect(tags(requester, "REQ-3011")).toHaveText("Real object");
  await expect(tags(requester, "REPLAY-3020")).toHaveText("Real objectReplay");

  const station = await signedIn(browser, STATION);
  await station.goto("/#/my-observations");
  await expect(tags(station, "SIM-REQ-3000")).toHaveText("SIMULATED");
  const replayStation = await signedIn(browser, REPLAY_STATION);
  await replayStation.goto("/#/my-observations");
  await expect(tags(replayStation, "REPLAY-3020")).toHaveText("Real objectReplay");

  const admin = await signedIn(browser, stackInfo().admin.party);
  await admin.goto("/#/admin");
  // The requests' table: the event log names requests too, without tags.
  const row = (id: string) =>
    admin
      .getByRole("row")
      .filter({ hasText: id, has: admin.getByTestId("label-tags") })
      .getByTestId("label-tags");
  await expect(row("SIM-REQ-3000")).toHaveText("SIMULATED");
  await expect(row("REPLAY-3020")).toHaveText("Real objectReplay");
});

test("a review task labels its files, without naming its request", async ({ browser }) => {
  const reviewer =
    (stackInfo() as unknown as { in_review: { reviewers: string[] } }).in_review.reviewers[0] ?? "";
  const page = await signedIn(browser, reviewer);
  const tasks = (await asParty(page.request, reviewer, "GET", "/v1/tasks")).json.tasks as {
    task_id: string;
  }[];
  await page.goto(`/#/tasks/${tasks[0]?.task_id ?? "none"}`);
  const labels = page.getByTestId("labels");
  await expect(labels).toContainText(OWN_ORBIT);
  await expect(labels).toContainText("SIMULATED, as the file says");
});

test("a new request says what each object on the list is", async ({ browser }) => {
  const page = await signedIn(browser, REQUESTER);
  await page.goto("/#/new-request");
  await expect(page.getByText("A SIMULATED object: the request is SIMULATED too.")).toBeVisible();
  await expect(page.getByLabel("SIMULATED observations")).toHaveCount(0);
  // The stand-in is a real object: the requester chooses, nothing ticked in advance.
  await page.getByLabel("Target").selectOption("339990");
  await expect(page.getByTestId("target-source")).toContainText(STAND_IN);
  await expect(page.getByLabel("SIMULATED observations")).not.toBeChecked();
});

test("the testnet label says that real and SIMULATED data run side by side", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("testnet-label")).toContainText(
    "SIMULATED and real data side by side",
  );
});
