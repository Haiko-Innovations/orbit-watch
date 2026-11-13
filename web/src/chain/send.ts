import {
  type Address,
  BaseError,
  createWalletClient,
  custom,
  decodeErrorResult,
  type EIP1193Provider,
  type Hex,
} from "viem";
import { postJson } from "../api";
import { strings } from "../strings";
import { CHAINS, isUserRejection, switchToChain, WalletError } from "../wallet/wallet";
import { escrowAbi } from "./abis";
import type { Described } from "./describe";

const t = strings.tx;

export interface TransactionView {
  tx_hash: string;
  party: string;
  action: string;
  request_id: string | null;
  status: "pending" | "confirmed" | "failed";
  block: number | null;
  error: string | null;
  explorer: string | null;
}

/** The revert data in an error from a wallet or node, if there is any. */
export function revertData(error: unknown): Hex | null {
  let found: Hex | null = null;
  const look = (value: unknown) => {
    const data = (value as { data?: unknown } | null)?.data;
    if (typeof data === "string" && /^0x[0-9a-fA-F]{8,}$/.test(data)) found = data as Hex;
    else if (data && typeof data === "object") look(data);
  };
  if (error instanceof BaseError) {
    error.walk((inner) => {
      look(inner);
      return found !== null;
    });
  } else {
    look(error);
  }
  return found;
}

/** Why the chain refuses a transaction, in words: the escrow's own error if it gave one. */
export function explainRevert(error: unknown): string | null {
  const data = revertData(error);
  if (data === null) {
    const text = error instanceof BaseError ? error.details || error.shortMessage : String(error);
    return /revert/i.test(text) ? t.reverted.unknown : null;
  }
  try {
    const { errorName } = decodeErrorResult({ abi: escrowAbi, data });
    return (
      t.reverted.known[errorName as keyof typeof t.reverted.known] ?? t.reverted.named(errorName)
    );
  } catch {
    return t.reverted.unknown;
  }
}

/** Whether the wallet cannot pay the network fee. */
export function lacksGas(error: unknown): boolean {
  const texts: string[] = [];
  const collect = (value: unknown) => {
    const { name, message, details } = (value ?? {}) as Record<string, unknown>;
    for (const text of [name, message, details]) if (typeof text === "string") texts.push(text);
  };
  if (error instanceof BaseError) {
    error.walk((inner) => {
      collect(inner);
      return false;
    });
  } else {
    collect(error);
  }
  return texts.some((text) =>
    /InsufficientFunds|insufficient funds|exceeds the balance of the account/i.test(text),
  );
}

/** Sends one transaction with the party's own wallet; returns its hash. */
export async function sendWithWallet(
  provider: EIP1193Provider,
  account: Address,
  described: Described,
): Promise<Hex> {
  const chain = CHAINS[described.transaction.chainId];
  if (!chain)
    throw new WalletError("wrong_chain", t.refused.chain(described.transaction.chainId, ""));
  await switchToChain(provider, chain.id);
  const wallet = createWalletClient({ account, chain, transport: custom(provider) });
  try {
    return await wallet.sendTransaction({
      account,
      chain,
      to: described.to,
      data: described.transaction.data,
      value: 0n,
    });
  } catch (error) {
    if (isUserRejection(error)) throw new WalletError("declined", t.declined);
    if (lacksGas(error)) throw new WalletError("failed", t.noGas);
    const reverted = explainRevert(error);
    if (reverted !== null) throw new WalletError("reverted", reverted);
    const detail = error instanceof BaseError ? error.shortMessage : String(error);
    throw new WalletError("failed", t.notSent(detail));
  }
}

/** Tells the service about a sent transaction; it waits for the chain and does its part. */
export async function report(hash: Hex): Promise<TransactionView> {
  const answer = await postJson<{ transaction: TransactionView }>(
    "/v1/transactions",
    { tx_hash: hash },
    { idempotencyKey: `report-${hash}` },
  );
  return answer.transaction;
}
