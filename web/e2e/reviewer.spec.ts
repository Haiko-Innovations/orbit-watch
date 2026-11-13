import AxeBuilder from "@axe-core/playwright";
import { type Browser, expect, type Page, test } from "@playwright/test";
import { asParty, stackInfo } from "./stack";
import { installTestWallet, localTestKey } from "./testWallet";

// The reviewer's view (phase 3, step 3.6), against the local stack: SIM-REQ-3006 is in
// review, and the escrow chose its three reviewers. They vote with LOCAL TEST keys; the
// observations are SIMULATED; nothing has value.

test.describe.configure({ mode: "serial" });

interface Round {
  request_id: string;
  reviewers: string[];
  delivery_sha256: string;
}

function round(): Round {
  return (stackInfo() as unknown as { in_review: Round }).in_review;
}

interface Task {
  task_id: string;
  observations_sha256: string;
}

async function tasksOf(page: Page, reviewer: string): Promise<Task[]> {
  return (await asParty(page.request, reviewer, "GET", "/v1/tasks")).json.tasks as Task[];
}

/** The SHA-256 of every delivered observation file: a task whose file is none of them is a
 * calibration task. The page itself cannot tell them apart, on purpose (decision D-23). */
async function deliveredFiles(page: Page): Promise<Set<string>> {
  const requester = "requester:sim-cubesat-team";
  const listed = (await asParty(page.request, requester, "GET", "/v1/requests")).json.requests as {
    request_id: string;
  }[];
  const hashes = new Set<string>();
  for (const { request_id } of listed) {
    const view = await asParty(page.request, requester, "GET", `/v1/requests/${request_id}`);
    const sha = (view.json.record as { delivery_sha256: string | null }).delivery_sha256;
    if (sha) hashes.add(sha);
  }
  return hashes;
}

async function signedIn(browser: Browser, reviewer: string): Promise<Page> {
  const page = await (await browser.newContext()).newPage();
  await installTestWallet(page, localTestKey(reviewer));
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: "Test wallet (LOCAL keys)" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
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

test("two reviewers vote in the browser as EAS attestations, and the round settles", async ({
  browser,
}) => {
  const { request_id, reviewers, delivery_sha256 } = round();
  const voters = reviewers.slice(0, 2);
  for (const [index, reviewer] of voters.entries()) {
    const page = await signedIn(browser, reviewer);
    await page.getByRole("link", { name: "Your review tasks" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Your review tasks" })).toBeVisible();
    // Its real task and a calibration task for this round, and maybe tasks of other rounds.
    const tasks = await tasksOf(page, reviewer);
    const delivered = await deliveredFiles(page);
    const real = tasks.find((task) => task.observations_sha256 === delivery_sha256);
    const calibration = tasks.find((task) => !delivered.has(task.observations_sha256));
    if (!real || !calibration) throw new Error(`${reviewer} lacks a task`);
    if (index === 0) await audit(page);

    await page.getByRole("link", { name: new RegExp(real.task_id) }).click();
    await expect(
      page.getByText("SIMULATED: the track may belong to the neighbouring CubeSat."),
    ).toBeVisible();
    await expect(page.getByText("Verdict: pass")).toBeVisible();
    if (index === 0) await audit(page);
    await page.getByLabel("Approve: the delivery meets the request").check();
    await page
      .getByLabel("Your reasons")
      .fill("SIMULATED: residuals follow SIM-CUBESAT-A's orbit.");
    await page.getByRole("button", { name: "Answer" }).click();
    const flow = page.getByRole("region", { name: "Check and send" });
    await expect(flow).toContainText(`Record your vote: approve the delivery for ${request_id}`);
    await expect(flow).toContainText("Ethereum Attestation Service");
    await flow.getByRole("button", { name: "Send with your wallet" }).click();
    await expect(flow).toContainText("Done. The chain confirmed every transaction.");
    await flow.getByRole("button", { name: "Close" }).click();
    await expect(page.getByText("Your answer is recorded.")).toBeVisible();

    if (index === 0) {
      // A calibration answer needs no transaction.
      await page.goto(`/#/tasks/${calibration.task_id}`);
      await page.getByLabel("Reject: it does not").check();
      await page.getByLabel("Your reasons").fill("SIMULATED: the positions drift from the target.");
      await page.getByRole("button", { name: "Answer" }).click();
      await expect(page.getByText("Your answer is recorded.")).toBeVisible();
    }
    await page.context().close();
  }

  // Two approvals of three decide the round; the service settles it on chain.
  const view = await asParty(
    (await browser.newContext()).request,
    "requester:sim-cubesat-team",
    "GET",
    `/v1/requests/${request_id}`,
  );
  const record = view.json.record as { status: string; outcome: string };
  expect(record).toMatchObject({ status: "settled", outcome: "accepted" });

  // The first reviewer sees the reward waiting and its record.
  const page = await signedIn(browser, voters[0] ?? "");
  await expect(page.locator("dl.details").nth(1)).toContainText("0.1 TESTUSD");
  await page.getByRole("link", { name: "Your review tasks" }).click();
  await expect(page.getByText("1 answered")).toBeVisible();
  await expect(page.getByText(/^1 in real rounds, 2 answers in all/)).toBeVisible();
});

test("a reviewer outside the round has no task for it and cannot open one", async ({ browser }) => {
  const { reviewers, delivery_sha256 } = round();
  const outsider = Object.keys(stackInfo().parties).find(
    (party) => party.startsWith("reviewer:") && !reviewers.includes(party),
  );
  if (!outsider) throw new Error("every reviewer is in the round");
  const page = await signedIn(browser, outsider);
  const own = await tasksOf(page, outsider);
  expect(own.some((task) => task.observations_sha256 === delivery_sha256)).toBe(false);

  const member = reviewers[2] ?? "";
  const theirs = (await tasksOf(page, member)).find(
    (task) => task.observations_sha256 === delivery_sha256,
  );
  await page.goto(`/#/tasks/${theirs?.task_id ?? "task-none"}`);
  await expect(page.getByText("This task is not among your open tasks")).toBeVisible();
  await expect(page.getByRole("button", { name: "Answer" })).toHaveCount(0);
});
