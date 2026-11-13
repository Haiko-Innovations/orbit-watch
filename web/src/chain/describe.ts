import {
  type Abi,
  type Address,
  decodeFunctionData,
  getAddress,
  type Hex,
  isAddressEqual,
  keccak256,
  toBytes,
} from "viem";
import type { ChainInfo } from "../api";
import { formatUnits } from "../format";
import { strings } from "../strings";
import { easAbi, escrowAbi, tokenAbi } from "./abis";

// What a prepared transaction does, read from its call data with the contracts' own
// interfaces (decision P3-06). Anything that is not a call this party may make to Orbit
// Watch's own contracts, on the service's chain, from the signed-in wallet, is refused
// before the wallet sees it.

const t = strings.tx;

export interface UnsignedTransaction {
  chainId: number;
  from: string;
  to: string;
  data: Hex;
  value: number | string;
}

export interface Prepared {
  request_id: string | null;
  action: string;
  sign: { action: string; transaction: UnsignedTransaction }[];
  notice: string;
}

export interface Described {
  title: string;
  detail: string | null;
  contract: string;
  to: Address;
  functionName: string;
  transaction: UnsignedTransaction;
}

export class RefusedTransaction extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RefusedTransaction";
  }
}

const REVIEWS_PER_ROUND = 3n; // the reviewer share pays a round of three (settlement rules 1.0)

function amount(units: bigint, chain: ChainInfo): string {
  return `${formatUnits(units, chain.token.decimals)} ${chain.token.symbol}`;
}

function decode(abi: Abi, data: Hex) {
  try {
    return decodeFunctionData({ abi, data });
  } catch {
    throw new RefusedTransaction(t.refused.unreadable);
  }
}

function describeOne(
  transaction: UnsignedTransaction,
  requestId: string | null,
  chain: ChainInfo,
  account: Address,
): Described {
  if (transaction.chainId !== chain.chain_id) {
    throw new RefusedTransaction(t.refused.chain(transaction.chainId, chain.network));
  }
  if (!isAddressEqual(transaction.from as Address, account)) {
    throw new RefusedTransaction(t.refused.sender(transaction.from));
  }
  if (BigInt(transaction.value) !== 0n) throw new RefusedTransaction(t.refused.value);
  const to = getAddress(transaction.to);
  const key = requestId === null ? null : keccak256(toBytes(requestId));
  const forRequest = (id: unknown) => {
    if (key === null || id !== key) throw new RefusedTransaction(t.refused.request);
  };
  const base = { to, transaction };

  if (isAddressEqual(to, chain.escrow as Address)) {
    const call = decode(escrowAbi, transaction.data);
    const args = (call.args ?? []) as readonly unknown[];
    const shown = { ...base, contract: t.contracts.escrow, functionName: call.functionName };
    switch (call.functionName) {
      case "withdraw":
        return { ...shown, title: t.withdraw.title, detail: t.withdraw.detail };
      case "fund": {
        forRequest(args[0]);
        const split = args[2] as {
          observerReward: bigint;
          reviewerReward: bigint;
          platformFee: bigint;
        };
        const total =
          split.observerReward + REVIEWS_PER_ROUND * split.reviewerReward + split.platformFee;
        return {
          ...shown,
          title: t.fund.title(requestId ?? "", amount(total, chain)),
          detail: t.fund.detail(
            amount(split.observerReward, chain),
            amount(split.reviewerReward, chain),
            amount(split.platformFee, chain),
          ),
        };
      }
      case "reserve":
      case "deliver":
      case "challenge":
      case "cancel":
      case "settle":
        forRequest(args[0]);
        return {
          ...shown,
          title: t.escrowCalls[call.functionName](requestId ?? ""),
          detail: null,
        };
      default:
        throw new RefusedTransaction(t.refused.function(call.functionName));
    }
  }

  if (isAddressEqual(to, chain.token.address as Address)) {
    const call = decode(tokenAbi, transaction.data);
    const args = (call.args ?? []) as readonly unknown[];
    if (
      call.functionName !== "approve" ||
      !isAddressEqual(args[0] as Address, chain.escrow as Address)
    ) {
      throw new RefusedTransaction(t.refused.function(call.functionName));
    }
    return {
      ...base,
      contract: t.contracts.token(chain.token.symbol),
      functionName: call.functionName,
      title: t.approve.title(amount(args[1] as bigint, chain)),
      detail: t.approve.detail,
    };
  }

  if (isAddressEqual(to, chain.eas as Address)) {
    const call = decode(easAbi, transaction.data);
    const request = ((call.args ?? []) as readonly unknown[])[0] as { schema?: Hex } | undefined;
    if (call.functionName !== "attest" || request?.schema !== chain.vote_schema) {
      throw new RefusedTransaction(t.refused.function(call.functionName));
    }
    return {
      ...base,
      contract: t.contracts.eas,
      functionName: call.functionName,
      title: t.vote.title(requestId ?? ""),
      detail: t.vote.detail,
    };
  }

  throw new RefusedTransaction(t.refused.contract(to));
}

/** Every transaction of ``prepared``, in order, described; or a RefusedTransaction. */
export function describePrepared(
  prepared: Prepared,
  chain: ChainInfo,
  account: Address,
): Described[] {
  if (prepared.sign.length === 0) throw new RefusedTransaction(t.refused.empty);
  return prepared.sign.map(({ transaction }) =>
    describeOne(transaction, prepared.request_id, chain, account),
  );
}
