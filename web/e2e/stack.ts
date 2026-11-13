import { readFileSync } from "node:fs";
import type { APIRequestContext } from "@playwright/test";
import { createWalletClient, type Hex, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { foundry } from "viem/chains";
import { CHAIN_RPC } from "./testWallet";

// The local stack as the end-to-end tests see it: the parties' API keys and LOCAL TEST keys
// from its local-stack.json in web/.e2e-stack (playwright.config.ts). With
// them a test plays the roles whose views come in later steps, through the API and the
// chain, as the command line would.

interface Party {
  key: string;
  address: string;
  private_key: Hex;
}

interface StackInfo {
  admin_key: string;
  parties: Record<string, Party>;
  /** Fresh SIMULATED good observations by station, never delivered yet. */
  datasets: Record<string, string[]>;
}

const INFO = new URL("../.e2e-stack/local-stack.json", import.meta.url);

export function stackInfo(): StackInfo {
  return JSON.parse(readFileSync(INFO, "utf8")) as StackInfo;
}

/** The ``index``th fresh good observation file of ``station``. */
export function freshObservations(station: string, index: number): Buffer {
  const path = stackInfo().datasets[station]?.[index];
  if (!path) throw new Error(`the local stack has no dataset ${index} for ${station}`);
  return readFileSync(path);
}

function keyOf(party: string): string {
  const info = stackInfo();
  return party === "admin" ? info.admin_key : (info.parties[party]?.key ?? "");
}

let counter = 0;

/** Calls the API as ``party`` (or "admin") with its API key. */
export async function asParty(
  request: APIRequestContext,
  party: string,
  method: "GET" | "POST",
  path: string,
  body?: string | Buffer | object,
  query?: Record<string, string>,
): Promise<{ status: number; json: Record<string, unknown> }> {
  counter += 1;
  const headers: Record<string, string> = { Authorization: `Bearer ${keyOf(party)}` };
  if (method === "POST") headers["Idempotency-Key"] = `e2e-${Date.now()}-${counter}`;
  const raw = typeof body === "string" || Buffer.isBuffer(body);
  const response = await request.fetch(path, {
    method,
    headers: raw ? { ...headers, "Content-Type": "application/octet-stream" } : headers,
    ...(body === undefined ? {} : raw ? { data: body } : { data: body }),
    ...(query ? { params: query } : {}),
  });
  return { status: response.status(), json: (await response.json()) as Record<string, unknown> };
}

interface Prepared {
  sign: { transaction: { to: Hex; data: Hex } }[];
}

/** Signs and sends prepared transactions with ``party``'s LOCAL TEST key, and reports them. */
export async function signAndReport(
  request: APIRequestContext,
  party: string,
  prepared: Prepared,
): Promise<void> {
  const secret = stackInfo().parties[party]?.private_key;
  if (!secret) throw new Error(`no test key for ${party}`);
  const wallet = createWalletClient({
    account: privateKeyToAccount(secret),
    chain: foundry,
    transport: http(CHAIN_RPC),
  });
  for (const { transaction } of prepared.sign) {
    const hash = await wallet.sendTransaction({ to: transaction.to, data: transaction.data });
    const reported = await asParty(request, party, "POST", "/v1/transactions", { tx_hash: hash });
    const status = (reported.json.transaction as { status?: string } | undefined)?.status;
    if (status !== "confirmed") throw new Error(`${party}: ${hash} is ${status}`);
  }
}

async function rpc(method: string, params: unknown[]): Promise<unknown> {
  const response = await fetch(CHAIN_RPC, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const answer = (await response.json()) as { result?: unknown; error?: unknown };
  if (answer.error) throw new Error(`${method}: ${JSON.stringify(answer.error)}`);
  return answer.result;
}

/** Gives ``address`` local test ether for gas, as a faucet would on a testnet. */
export async function giveGasMoney(address: string): Promise<void> {
  await rpc("anvil_setBalance", [address, "0x3635c9adc5dea00000"]); // 1000 local test ETH
}

/** Moves the local chain's clock forward, as core/src/orbit_watch/chain/client.py does. */
export async function travelTo(iso: string): Promise<void> {
  const target = Math.floor(new Date(iso).getTime() / 1000);
  const latest = await rpc("eth_getBlockByNumber", ["latest", false]);
  let now = Number.parseInt((latest as { timestamp: string }).timestamp, 16);
  if (target > now) {
    await rpc("evm_mine", [target]);
    now = target;
  }
  await rpc("evm_setNextBlockTimestamp", [now]);
}
