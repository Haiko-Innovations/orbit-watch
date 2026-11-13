import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import {
  type APIRequestContext,
  type Browser,
  type BrowserContext,
  expect,
  type Page,
  test,
} from "@playwright/test";
import {
  createPublicClient,
  createWalletClient,
  type Hex,
  http,
  parseAbi,
  type WalletClient,
} from "viem";
import { privateKeyToAccount, sign } from "viem/accounts";
import { baseSepolia } from "viem/chains";
import { installTestWallet } from "../e2e/testWallet";
import { openKeystore } from "./keystore";

// The phase 3 demo (step 3.8): the whole chain in the browser on Base Sepolia, each role
// with its own wallet, recorded (web/demo/README.md). TESTNET ONLY, no real value: the token
// is Circle's test USDC, every station, observation, request and reviewer is SIMULATED, and
// the keys are the testnet keys of decision D-24, opened in this runner and never shown to
// the page, the service or the output.
//
// It writes examples/phase3 (transcript, summary, screenshots and the Safe batch file) and
// videos of every role's browser into $ORBIT_WATCH_DEMO_DIR/videos.

const SECRETS = process.env.ORBIT_WATCH_SECRETS ?? "";
const DIR = process.env.ORBIT_WATCH_DEMO_DIR ?? "";
const RPC = process.env.ORBIT_WATCH_DEMO_RPC ?? "https://sepolia.base.org";
const REQUEST = process.env.ORBIT_WATCH_DEMO_REQUEST ?? "SIM-REQ-3801";
const OUT = fileURLToPath(new URL("../../examples/phase3/", import.meta.url));
const WALLET = "Demo wallet (Base Sepolia testnet keys)";
const VIEWPORT = { width: 1280, height: 800 };
const network = { chain: baseSepolia, rpc: RPC };
const REQUESTER = "requester:sim-cubesat-team";
const STATION = "station:SIM-ESPOO";
const ADMIN = "admin:orbit-watch-demo";
const REVIEWERS = ["aino", "chen", "eero", "fatima"].map((name) => `reviewer:sim-${name}`);
// Not in the registry yet: the demo proposes adding it through the Safe and the timelock.
// (An earlier run scheduled sim-bertil; see examples/phase3/README.md.)
const NEWCOMER = process.env.ORBIT_WATCH_DEMO_NEWCOMER ?? "sim/reviewer-sim-dana";
const QUALITY_FILE = fileURLToPath(
  new URL("../../examples/simulated/datasets/acceptable/observations.json", import.meta.url),
);

test.describe.configure({ mode: "serial" });

interface Shot {
  file: string;
  caption: string;
}

interface Step {
  who: string;
  what: string;
  shots: Shot[];
}

const steps: Step[] = [];
const videos: { who: string; context: BrowserContext; page: Page }[] = [];
let shotCount = 0;

function step(who: string, what: string): Step {
  const made = { who, what, shots: [] };
  steps.push(made);
  return made;
}

async function shot(page: Page, into: Step, name: string, caption: string): Promise<void> {
  // Nothing half-loaded in the record.
  await expect(page.getByText("Loading…")).toHaveCount(0);
  shotCount += 1;
  const file = `screenshots/${String(shotCount).padStart(2, "0")}-${name}.jpg`;
  await page.screenshot({ path: `${OUT}${file}`, type: "jpeg", quality: 70 });
  into.shots.push({ file, caption });
}

function secrets(): { password: string; addresses: Record<string, Hex> } {
  return {
    password: readFileSync(`${SECRETS}/password`, "utf8").trim(),
    addresses: JSON.parse(readFileSync(`${SECRETS}/addresses.json`, "utf8")) as Record<string, Hex>,
  };
}

/** A party's testnet key, from its keystore (sim/<role>-<name>.json). */
function keyOf(keystore: string): Hex {
  return openKeystore(`${SECRETS}/${keystore}.json`, secrets().password);
}

function keystoreOf(party: string): string {
  const [role, name] = party.split(":");
  return `sim/${role}-${name}`;
}

const adminKey = () => readFileSync(`${DIR}/admin.key`, "utf8").trim();

let counter = 0;

async function api(
  request: APIRequestContext,
  method: "GET" | "POST",
  path: string,
  key: string,
  body?: object,
): Promise<Record<string, unknown>> {
  counter += 1;
  const response = await request.fetch(path, {
    method,
    headers: {
      Authorization: `Bearer ${key}`,
      ...(method === "POST" ? { "Idempotency-Key": `demo-${Date.now()}-${counter}` } : {}),
    },
    ...(body ? { data: body } : {}),
  });
  const json = (await response.json()) as Record<string, unknown>;
  expect(response.ok(), `${method} ${path}: ${JSON.stringify(json)}`).toBe(true);
  return json;
}

/** The administrator gives a party an API key and registers its wallet, as with the
 * command line: the wallet's owner signs the service's message. Reviewers come this way,
 * not by signing up (decision P3-05). */
async function registerWallet(request: APIRequestContext, party: string, key: Hex) {
  const role = party.split(":")[0] ?? "";
  const partyKey =
    party === ADMIN
      ? adminKey()
      : String((await api(request, "POST", "/v1/admin/keys", adminKey(), { party, role })).key);
  const view = await api(request, "GET", "/v1/wallet", partyKey);
  const account = privateKeyToAccount(key);
  const signature = await account.signMessage({ message: String(view.message) });
  await api(request, "POST", "/v1/wallet", partyKey, { address: account.address, signature });
}

async function browserOf(browser: Browser, who: string, key?: Hex): Promise<Page> {
  const context = await browser.newContext({
    viewport: VIEWPORT,
    recordVideo: { dir: `${DIR}/videos/raw`, size: VIEWPORT },
  });
  const page = await context.newPage();
  if (key) await installTestWallet(page, key, { name: WALLET, network });
  videos.push({ who, context, page });
  return page;
}

async function signIn(page: Page) {
  await page.goto("/#/sign-in");
  await page.getByRole("button", { name: WALLET }).click();
}

async function sendAll(page: Page, expected: string | RegExp) {
  const flow = page.getByRole("region", { name: "Check and send" });
  await expect(flow).toContainText(expected);
  // After a reload the page asks which wallet to send with; choosing it sends.
  const send = flow.getByRole("button", { name: "Send with your wallet" });
  const choose = flow.getByRole("button", { name: WALLET });
  await expect(send.or(choose)).toBeVisible();
  await ((await send.isVisible()) ? send : choose).click();
  await expect(flow).toContainText("Done. The chain confirmed every transaction.");
  await flow.getByRole("button", { name: "Close" }).click();
}

function utcInput(date: Date): string {
  return date.toISOString().slice(0, 16);
}

const SAFE_ABI = parseAbi([
  "function nonce() view returns (uint256)",
  "function getTransactionHash(address to, uint256 value, bytes data, uint8 operation, uint256 safeTxGas, uint256 baseGas, uint256 gasPrice, address gasToken, address refundReceiver, uint256 _nonce) view returns (bytes32)",
  "function execTransaction(address to, uint256 value, bytes data, uint8 operation, uint256 safeTxGas, uint256 baseGas, uint256 gasPrice, address gasToken, address refundReceiver, bytes signatures) payable returns (bool success)",
]);
const ZERO: Hex = "0x0000000000000000000000000000000000000000";

/** What two of the Safe's three owners do in the Safe app: sign the Safe transaction's hash
 * and execute it. Here their testnet keys sign in this runner. */
async function safeExecutes(safe: Hex, to: Hex, data: Hex): Promise<Hex> {
  const chain = createPublicClient({ chain: baseSepolia, transport: http(RPC) });
  const nonce = await chain.readContract({ address: safe, abi: SAFE_ABI, functionName: "nonce" });
  const hash = await chain.readContract({
    address: safe,
    abi: SAFE_ABI,
    functionName: "getTransactionHash",
    args: [to, 0n, data, 0, 0n, 0n, 0n, ZERO, ZERO, nonce],
  });
  const owners = ["safe-1", "safe-2"]
    .map((name) => keyOf(name))
    .map((key) => ({ key, address: privateKeyToAccount(key).address }))
    .sort((a, b) => (BigInt(a.address) < BigInt(b.address) ? -1 : 1));
  let signatures = "0x";
  for (const owner of owners) {
    signatures += (await sign({ hash, privateKey: owner.key, to: "hex" })).slice(2);
  }
  const sender: WalletClient = createWalletClient({
    account: privateKeyToAccount(keyOf("safe-1")),
    chain: baseSepolia,
    transport: http(RPC),
  });
  const tx = await sender.writeContract({
    address: safe,
    abi: SAFE_ABI,
    functionName: "execTransaction",
    args: [to, 0n, data, 0, 0n, 0n, 0n, ZERO, ZERO, signatures as Hex],
    account: sender.account ?? null,
    chain: baseSepolia,
  });
  const receipt = await chain.waitForTransactionReceipt({ hash: tx });
  if (receipt.status !== "success") throw new Error(`the Safe transaction ${tx} failed`);
  return tx;
}

test("the whole chain in the browser on Base Sepolia", async ({ browser, request }) => {
  if (!SECRETS || !DIR) throw new Error("set ORBIT_WATCH_SECRETS and ORBIT_WATCH_DEMO_DIR");
  mkdirSync(`${OUT}screenshots`, { recursive: true });
  const { addresses } = secrets();

  // ---------------------------------------------------------------- set-up
  const setup = step(
    "administrator (command line)",
    "Registers the reviewers' wallets, and its own, with the service.",
  );
  for (const reviewer of REVIEWERS) {
    await registerWallet(request, reviewer, keyOf(keystoreOf(reviewer)));
  }
  await registerWallet(request, ADMIN, keyOf("sim/admin-orbit-watch-demo"));
  setup.what += ` Reviewers: ${REVIEWERS.join(", ")}.`;

  // ---------------------------------------------------------------- public
  const visitor = await browserOf(browser, "visitor");
  await visitor.goto("/");
  await expect(visitor.getByTestId("testnet-label")).toContainText("Base Sepolia testnet");
  await shot(
    visitor,
    step("visitor", "Opens the network page: Base Sepolia, the contracts, no sign-in."),
    "network",
    "The network page on Base Sepolia, with the testnet label.",
  );

  // ---------------------------------------------------------------- the requester
  const requester = await browserOf(browser, "requester", keyOf(keystoreOf(REQUESTER)));
  await signIn(requester);
  await requester.getByLabel("a requester: I ask for observations").check();
  await requester.getByLabel("Name").fill("sim-cubesat-team");
  const signUp = step(REQUESTER, "Signs up with its own wallet (Sign-In with Ethereum).");
  await shot(requester, signUp, "sign-up", "Signing up as a requester with the wallet.");
  await requester.getByRole("button", { name: "Sign up and sign in" }).click();
  await expect(requester.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();

  await requester.getByRole("link", { name: "Your requests" }).click();
  await requester.getByRole("link", { name: "New request" }).click();
  await requester.getByLabel("Request ID").fill(REQUEST);
  await requester
    .getByLabel("Title")
    .fill("SIMULATED: track SIM-CUBESAT-A on Base Sepolia (phase 3 demo)");
  await requester.getByLabel("Observation window starts (UTC)").fill("2026-11-01T15:00");
  await requester.getByLabel("Observation window ends (UTC)").fill("2026-11-02T03:00");
  await requester
    .getByLabel("Delivery deadline (UTC)")
    .fill(utcInput(new Date(Date.now() + 90 * 60_000)));
  await requester.getByLabel("A reservation lasts (hours)").fill("1");
  await requester.getByLabel("Challenge period (hours)").fill("1");
  await requester.getByLabel("Reviewer round (hours)").fill("1");
  const create = step(
    REQUESTER,
    `Creates ${REQUEST}: SIM-CUBESAT-A, the window of 1-2 November 2026, minutes-long deadlines; publishes it and deposits its rewards.`,
  );
  await shot(requester, create, "new-request", "The new request's form.");
  await requester.getByRole("button", { name: "Create draft" }).click();
  await requester.getByRole("button", { name: "Publish" }).click();
  await expect(requester.locator(".status-line")).toContainText("Published, waiting for funding");
  await requester.getByRole("button", { name: "Prepare the deposit" }).click();
  await expect(requester.getByRole("region", { name: "Check and send" })).toContainText(
    `Deposit 1.3 USDC for ${REQUEST}`,
  );
  await shot(
    requester,
    create,
    "deposit-check",
    "Before the wallet: what each transaction does, read from its call data.",
  );
  await sendAll(requester, "Allow the escrow to take 1.3 USDC");
  await expect(requester.locator(".status-line")).toContainText("Funded, waiting for an observer");
  await shot(requester, create, "funded", "Funded: the deposit is in the escrow.");

  // ---------------------------------------------------------------- the observer
  const station = await browserOf(browser, "station", keyOf(keystoreOf(STATION)));
  await signIn(station);
  await station.getByLabel("an observer: I run a station").check();
  await station.getByLabel("Name").fill("SIM-ESPOO");
  await station.getByRole("button", { name: "Sign up and sign in" }).click();
  await expect(station.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
  await station.getByRole("link", { name: "Your station" }).click();
  await station.getByLabel("Start from").selectOption("sim-cmos-gps");
  await station.getByRole("button", { name: "Save the profile" }).click();
  await expect(station.getByRole("status")).toContainText("Saved.");
  const observe = step(
    STATION,
    "Signs up, registers its SIMULATED station, reserves the request, simulates observations with its profile and delivers them.",
  );
  await shot(station, observe, "station", "The station's SIMULATED profile.");
  await station.getByRole("link", { name: "Open requests" }).click();
  await station.getByRole("button", { name: `Reserve ${REQUEST}` }).click();
  await sendAll(station, `Reserve ${REQUEST}`);
  await station.getByRole("button", { name: "Simulate observations with your station" }).click();
  await expect(station.getByTestId("delivery-sha256")).toHaveText(/^[0-9a-f]{64}$/);
  await station.getByRole("button", { name: "Prepare the delivery" }).click();
  await sendAll(station, `Record your delivery for ${REQUEST}`);
  await expect(station.locator(".status-line")).toContainText("the challenge period is running");
  await expect(station.getByText("Verdict: pass")).toBeVisible();
  await shot(station, observe, "verified", "Delivered and verified, check by check.");

  // ---------------------------------------------------------------- a challenge
  // The requester's page still shows the funded request: load it afresh.
  await requester.goto(`/#/requests/${REQUEST}`);
  await requester.reload();
  await expect(requester.locator(".status-line")).toContainText("the challenge period is running");
  await requester
    .getByLabel("Reason")
    .fill("SIMULATED: the track may belong to the neighbouring CubeSat.");
  await requester.getByRole("button", { name: "Prepare the challenge" }).click();
  await sendAll(requester, `Challenge the result of ${REQUEST}`);
  await expect(requester.getByText(/Reviewers chosen by the escrow: reviewer:sim-/)).toBeVisible();
  const challenge = step(
    REQUESTER,
    "Challenges the passed result; the escrow chooses three reviewers from the registry.",
  );
  await shot(requester, challenge, "challenged", "Challenged: three reviewers chosen on chain.");
  const view = (await requester.request.get(`/v1/requests/${REQUEST}`).then((r) => r.json())) as {
    record: { reviewers: string[]; delivery_sha256: string };
  };
  const chosen = view.record.reviewers;

  // ---------------------------------------------------------------- two reviewers vote
  for (const [index, reviewer] of chosen.slice(0, 2).entries()) {
    const page = await browserOf(browser, reviewer, keyOf(keystoreOf(reviewer)));
    await signIn(page);
    await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
    await page.getByRole("link", { name: "Your review tasks" }).click();
    const tasks = (await page.request.get("/v1/tasks").then((r) => r.json())) as {
      tasks: { task_id: string; observations_sha256: string }[];
    };
    const real = tasks.tasks.find((t) => t.observations_sha256 === view.record.delivery_sha256);
    if (!real) throw new Error(`${reviewer} has no task for ${REQUEST}`);
    await page.goto(`/#/tasks/${real.task_id}`);
    await expect(page.getByText("Verdict: pass")).toBeVisible();
    await page.getByLabel("Approve: the delivery meets the request").check();
    await page
      .getByLabel("Your reasons")
      .fill("SIMULATED: the residuals follow SIM-CUBESAT-A's orbit, not its neighbour's.");
    await page.getByRole("button", { name: "Answer" }).click();
    const vote = step(reviewer, "Approves with reasons: its vote is an EAS attestation it signs.");
    if (index === 0) await shot(page, vote, "vote-check", "The vote, checked before signing.");
    await sendAll(page, `Record your vote: approve the delivery for ${REQUEST}`);
    await expect(page.getByText("Your answer is recorded.")).toBeVisible();
  }

  // ---------------------------------------------------------------- settlement
  await requester.reload();
  await expect(requester.locator(".status-line")).toContainText("Settled · Outcome: accepted");
  await expect(requester.getByText("Verdict: pass")).toBeVisible();
  const settled = step(
    "service (verifier key)",
    "Two approvals of three decide the round; the service settles the request on chain.",
  );
  await shot(requester, settled, "settled", "Settled: who gets what, and the chain's events.");

  // ---------------------------------------------------------------- withdrawals
  for (const [who, page] of [
    [STATION, station],
    [REQUESTER, requester],
  ] as const) {
    await page.getByRole("link", { name: who }).click();
    await expect(page.getByRole("heading", { level: 1, name: "Your account" })).toBeVisible();
    const withdraw = page.getByRole("button", { name: /^Withdraw \d/ });
    await expect(withdraw.or(page.getByText("Nothing to withdraw."))).toBeVisible();
    if ((await withdraw.count()) === 0) continue; // nothing came back to it
    await withdraw.click();
    await sendAll(page, "Withdraw your credit");
    await expect(page.getByText("Nothing to withdraw.")).toBeVisible();
    const withdrew = step(who, "Withdraws its credit from the escrow with its own wallet.");
    if (who === STATION) {
      await shot(page, withdrew, "withdrawn", "The reward withdrawn; the transactions listed.");
    }
  }

  // ---------------------------------------------------------------- the administrator
  const admin = await browserOf(browser, "administrator", keyOf("sim/admin-orbit-watch-demo"));
  await signIn(admin);
  await admin.getByRole("link", { name: "Administration" }).click();
  await expect(
    admin.getByRole("table", { name: "Requests" }).getByRole("row").filter({ hasText: REQUEST }),
  ).toContainText("Settled");
  const overview = step(
    ADMIN,
    "Signs in with its wallet: every request, payment, transaction and event; runs the simulator; prepares adding a reviewer for the Safe.",
  );
  await shot(admin, overview, "admin", "The administrator view.");
  const simulator = admin.getByRole("form", { name: "Simulator" });
  await simulator.getByRole("button", { name: "Simulate" }).click();
  await expect(simulator).toContainText(/\d+ SIMULATED observations\./);

  const newcomer = addresses[NEWCOMER] ?? ZERO;
  await admin.getByLabel("Add a reviewer").check();
  await admin.getByLabel("Reviewer: wallet address or party name").fill(newcomer);
  await admin.getByRole("button", { name: "Prepare the Safe transaction" }).click();
  const prepared = admin.getByRole("status").filter({ hasText: "Prepared:" });
  await expect(prepared).toContainText(`Prepared: addReviewer(${newcomer})`);
  await shot(admin, overview, "safe-proposal", "The Safe transaction, prepared for the Safe app.");
  const waiting = admin.waitForEvent("download");
  await prepared.getByRole("link", { name: "Download the batch file" }).click();
  const batchPath = `${OUT}safe-batch-add-reviewer.json`;
  copyFileSync(await (await waiting).path(), batchPath);
  const batch = JSON.parse(readFileSync(batchPath, "utf8")) as {
    meta: { createdFromSafeAddress: Hex };
    transactions: { to: Hex; data: Hex }[];
  };
  const [schedule] = batch.transactions;
  if (!schedule) throw new Error("the batch file has no transaction");

  const scheduled = await safeExecutes(
    batch.meta.createdFromSafeAddress,
    schedule.to,
    schedule.data,
  );
  const safeStep = step(
    "Safe owners (2 of 3)",
    `Schedule the batch file's transaction in the timelock: ${scheduled}. Anyone may execute it after 48 hours.`,
  );
  await admin.getByRole("button", { name: "Refresh" }).click();
  const operation = admin
    .getByRole("listitem")
    .filter({ hasText: `registry.addReviewer(${newcomer})` });
  await expect(operation).toContainText("Waiting");
  await operation.scrollIntoViewIfNeeded();
  await shot(admin, safeStep, "timelock", "The timelock's operation, waiting out its 48 hours.");

  // ---------------------------------------------------------------- public pages
  const reader = await browserOf(browser, "visitor (public pages)");
  await reader.goto("/#/attestations");
  const scan = reader.locator('a[href^="https://base-sepolia.easscan.org/attestation/view/0x"]');
  await expect(scan).toHaveCount(3); // the automated result and two votes
  await shot(
    reader,
    step("visitor", "Browses the attestations, with EAS Scan links, without signing in."),
    "attestations",
    "The attestation browser.",
  );
  await reader.goto("/#/quality");
  await reader.getByLabel("Observation file").setInputFiles(QUALITY_FILE);
  await reader.getByRole("button", { name: "Measure" }).click();
  await expect(reader.getByRole("region", { name: /^Station: / })).toContainText(
    "All observations",
  );
  await shot(
    reader,
    step("visitor", "Measures a SIMULATED observation file's quality without signing in."),
    "quality",
    "The station quality meter.",
  );

  // ---------------------------------------------------------------- the record
  const everything = await api(request, "GET", "/v1/admin/overview", adminKey());
  const attestations = await api(request, "GET", "/v1/public/attestations", adminKey());
  const governance = await api(request, "GET", "/v1/admin/governance", adminKey());
  writeRecord(everything, attestations, governance);

  for (const [index, { who, context, page }] of videos.entries()) {
    const video = page.video();
    await context.close();
    if (video) {
      mkdirSync(`${DIR}/videos`, { recursive: true });
      const name = `${String(index + 1).padStart(2, "0")}-${who.replace(/[^a-z0-9-]+/gi, "-")}.webm`;
      copyFileSync(await video.path(), `${DIR}/videos/${name}`);
    }
  }
});

interface Tx {
  tx_hash: string;
  party: string;
  action: string;
  request_id: string | null;
  status: string;
  block: number | null;
  explorer: string | null;
}

function writeRecord(
  overview: Record<string, unknown>,
  public_: Record<string, unknown>,
  governance: Record<string, unknown>,
) {
  const transactions = [...(overview.transactions as Tx[])].reverse();
  const attestations = public_.attestations as {
    uid: string;
    kind: string;
    request_id: string;
    by_service: boolean;
    attester: string;
    eas_scan: string | null;
  }[];
  const explorer = String(governance.explorer ?? "");
  const operations = governance.operations as {
    operation_id: string;
    state: string;
    ready_at: string | null;
    scheduled_tx: string;
    calls: { description: string }[];
  }[];
  const request = (overview.requests as { request_id: string }[]).find(
    (r) => r.request_id === REQUEST,
  );
  const summary = {
    notice:
      "Base Sepolia testnet, no real value. Every station, observation, request and reviewer is SIMULATED.",
    request: REQUEST,
    outcome: request,
    transactions,
    attestations,
    operations,
    steps,
  };
  writeFileSync(`${OUT}summary.json`, `${JSON.stringify(summary, null, 2)}\n`);

  const lines = [
    "# Phase 3 demo on Base Sepolia: transcript",
    "",
    "> **Base Sepolia testnet, no real value.** The token is Circle's test USDC. Every",
    "> station, observation, request and reviewer is SIMULATED. Written by",
    "> `web/demo/base-sepolia.demo.ts` ([README](README.md)).",
    "",
    `Request **${REQUEST}**: every role in its own browser with its own wallet.`,
    "",
    "## Steps",
    "",
  ];
  for (const [index, item] of steps.entries()) {
    lines.push(`${index + 1}. **${item.who}**: ${item.what}`);
    for (const { file, caption } of item.shots) {
      lines.push(`   - [${caption}](${file})`);
    }
  }
  lines.push("", "## Transactions", "", "| Party | Action | Request | Status | Transaction |");
  lines.push("|---|---|---|---|---|");
  for (const tx of transactions) {
    const link = tx.explorer ? `[\`${tx.tx_hash.slice(0, 18)}…\`](${tx.explorer})` : tx.tx_hash;
    lines.push(`| ${tx.party} | ${tx.action} | ${tx.request_id ?? "–"} | ${tx.status} | ${link} |`);
  }
  lines.push(
    "",
    "## Attestations",
    "",
    "| Request | Kind | By | Attestation |",
    "|---|---|---|---|",
  );
  for (const a of attestations) {
    const by = a.by_service ? "service (verifier key)" : a.attester;
    const link = a.eas_scan ? `[\`${a.uid.slice(0, 18)}…\`](${a.eas_scan})` : a.uid;
    lines.push(`| ${a.request_id} | ${a.kind} | ${by} | ${link} |`);
  }
  lines.push("", "## The timelock", "");
  for (const op of operations) {
    lines.push(
      `- \`${op.operation_id}\`: ${op.calls.map((c) => c.description).join("; ")}, ${op.state}` +
        (op.ready_at ? `, ready from ${op.ready_at}` : "") +
        `; scheduled by the Safe in [\`${op.scheduled_tx.slice(0, 18)}…\`](${explorer}/tx/${op.scheduled_tx}).`,
    );
  }
  lines.push(
    "",
    "The Safe's batch file the administrator view prepared: [safe-batch-add-reviewer.json](safe-batch-add-reviewer.json).",
    "",
  );
  writeFileSync(`${OUT}transcript.md`, lines.join("\n"));
}
