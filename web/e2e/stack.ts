import { readFileSync } from "node:fs";
import type { APIRequestContext } from "@playwright/test";
import { createPublicClient, createWalletClient, type Hex, http, parseAbi } from "viem";
import { privateKeyToAccount, sign } from "viem/accounts";
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

/** As on Base Sepolia: a timelock owns the reviewer registry, a 2-of-3 Safe proposes. */
interface Governance {
  registry: Hex;
  timelock: Hex;
  min_delay_seconds: number;
  safe: Hex;
  threshold: number;
  signers: { name: string; address: Hex; private_key: Hex }[];
}

interface StackInfo {
  admin_key: string;
  admin: Party & { party: string };
  governance: Governance;
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

const SAFE_ABI = parseAbi([
  "function nonce() view returns (uint256)",
  "function getTransactionHash(address to, uint256 value, bytes data, uint8 operation, uint256 safeTxGas, uint256 baseGas, uint256 gasPrice, address gasToken, address refundReceiver, uint256 _nonce) view returns (bytes32)",
  "function execTransaction(address to, uint256 value, bytes data, uint8 operation, uint256 safeTxGas, uint256 baseGas, uint256 gasPrice, address gasToken, address refundReceiver, bytes signatures) payable returns (bool success)",
]);
const ZERO: Hex = "0x0000000000000000000000000000000000000000";

/** What the Safe's owners do in the Safe app: ``threshold`` LOCAL TEST signers sign the
 * Safe transaction's hash, and one of them executes it. */
export async function safeExecute(to: Hex, data: Hex): Promise<void> {
  const { safe, signers, threshold } = stackInfo().governance;
  const chain = createPublicClient({ chain: foundry, transport: http(CHAIN_RPC) });
  const nonce = await chain.readContract({ address: safe, abi: SAFE_ABI, functionName: "nonce" });
  const hash = await chain.readContract({
    address: safe,
    abi: SAFE_ABI,
    functionName: "getTransactionHash",
    args: [to, 0n, data, 0, 0n, 0n, 0n, ZERO, ZERO, nonce],
  });
  // The Safe wants the signatures ordered by their owners' addresses.
  const chosen = signers
    .slice(0, threshold)
    .sort((a, b) => (BigInt(a.address) < BigInt(b.address) ? -1 : 1));
  let signatures = "0x";
  for (const signer of chosen) {
    signatures += (await sign({ hash, privateKey: signer.private_key, to: "hex" })).slice(2);
  }
  const first = chosen[0];
  if (!first) throw new Error("the Safe has no signers");
  const wallet = createWalletClient({
    account: privateKeyToAccount(first.private_key),
    chain: foundry,
    transport: http(CHAIN_RPC),
  });
  const tx = await wallet.writeContract({
    address: safe,
    abi: SAFE_ABI,
    functionName: "execTransaction",
    args: [to, 0n, data, 0, 0n, 0n, 0n, ZERO, ZERO, signatures as Hex],
  });
  const receipt = await chain.waitForTransactionReceipt({ hash: tx });
  if (receipt.status !== "success") throw new Error(`the Safe transaction ${tx} failed`);
}

/** Sends ``data`` to ``to`` from ``key``'s account (anyone may execute a ready operation). */
export async function sendFrom(key: Hex, to: Hex, data: Hex): Promise<void> {
  const chain = createPublicClient({ chain: foundry, transport: http(CHAIN_RPC) });
  const wallet = createWalletClient({
    account: privateKeyToAccount(key),
    chain: foundry,
    transport: http(CHAIN_RPC),
  });
  const tx = await wallet.sendTransaction({ to, data });
  const receipt = await chain.waitForTransactionReceipt({ hash: tx });
  if (receipt.status !== "success") throw new Error(`${tx} failed`);
}
