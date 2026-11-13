import { encodeAbiParameters, encodeFunctionData, type Hex, keccak256, toBytes } from "viem";
import { describe, expect, it } from "vitest";
import type { ChainInfo } from "../api";
import { easAbi, escrowAbi, tokenAbi } from "./abis";
import { describePrepared, type Prepared, RefusedTransaction } from "./describe";

const ACCOUNT = "0x4803e651A89F3160Ab9b82Db7a8f9Ed25269AC62";
const OTHER = "0x0000000000000000000000000000000000000Bad";
const VOTE_SCHEMA = `0x${"11".repeat(32)}` as Hex;
const RESULT_SCHEMA = `0x${"22".repeat(32)}` as Hex;

const chain: ChainInfo = {
  chain_id: 31337,
  network: "local Anvil chain",
  notice: "local Anvil test chain, no real value",
  escrow: "0x4C358435e5ad583B9290c801Bfd7DdaBc8BA9ee3",
  registry: "0x2b0F45b9002240Dcf70bE5f1ECa09f92837a03c4",
  token: { address: "0xdBd0E83a33A3a772cEb3421Cb547395fA3CD5DAe", symbol: "TESTUSD", decimals: 6 },
  eas: "0x4200000000000000000000000000000000000021",
  result_schema: RESULT_SCHEMA,
  vote_schema: VOTE_SCHEMA,
  verifier: "0x9af96e16C6447D60b0A447B6e8903f8318d4eaCa",
  fee_recipient: "0xbfa1C43A270302E3c0CA904A2a80EC6aDD93E88E",
  explorer: null,
  local: true,
  synced_block: 8,
};

function prepared(to: string, data: Hex, requestId: string | null = null, extra = {}): Prepared {
  return {
    request_id: requestId,
    action: "test",
    sign: [
      {
        action: "test",
        transaction: { chainId: 31337, from: ACCOUNT, to, data, value: 0, ...extra },
      },
    ],
    notice: chain.notice,
  };
}

const withdraw = encodeFunctionData({ abi: escrowAbi, functionName: "withdraw" });
const key = (id: string) => keccak256(toBytes(id));

function refusal(item: Prepared): string {
  try {
    describePrepared(item, chain, ACCOUNT);
  } catch (error) {
    expect(error).toBeInstanceOf(RefusedTransaction);
    return (error as Error).message;
  }
  throw new Error("not refused");
}

describe("describePrepared", () => {
  it("reads a withdrawal", () => {
    const [item] = describePrepared(prepared(chain.escrow, withdraw), chain, ACCOUNT);
    expect(item).toMatchObject({
      title: "Withdraw your credit",
      contract: "Orbit Watch escrow",
      functionName: "withdraw",
      to: chain.escrow,
    });
  });

  it("reads the amounts of a deposit from the call data", () => {
    const approve = encodeFunctionData({
      abi: tokenAbi,
      functionName: "approve",
      args: [chain.escrow, 1_300_000n],
    });
    const fund = encodeFunctionData({
      abi: escrowAbi,
      functionName: "fund",
      args: [
        key("SIM-REQ-3001"),
        {
          termsHash: `0x${"33".repeat(32)}`,
          deliveryDeadline: 1n,
          reservationSeconds: 1,
          verificationTimeoutSeconds: 1,
          challengeSeconds: 1,
          reviewSeconds: 1,
        },
        { observerReward: 1_000_000n, reviewerReward: 100_000n, platformFee: 0n },
      ],
    });
    const two: Prepared = {
      ...prepared(chain.token.address, approve, "SIM-REQ-3001"),
      sign: [
        prepared(chain.token.address, approve).sign[0] as Prepared["sign"][number],
        prepared(chain.escrow, fund).sign[0] as Prepared["sign"][number],
      ],
    };
    const [first, second] = describePrepared(two, chain, ACCOUNT);
    expect(first?.title).toBe("Allow the escrow to take 1.3 TESTUSD");
    expect(second?.title).toBe("Deposit 1.3 TESTUSD for SIM-REQ-3001");
    expect(second?.detail).toContain("three review rewards of 0.1 TESTUSD");
  });

  it("reads a vote, and only a vote, to EAS", () => {
    const attest = (schema: Hex) =>
      encodeFunctionData({
        abi: easAbi,
        functionName: "attest",
        args: [
          {
            schema,
            data: {
              recipient: ACCOUNT,
              expirationTime: 0n,
              revocable: false,
              refUID: `0x${"44".repeat(32)}`,
              data: encodeAbiParameters([{ type: "bool" }], [true]),
              value: 0n,
            },
          },
        ],
      });
    const [vote] = describePrepared(
      prepared(chain.eas, attest(VOTE_SCHEMA), "SIM-REQ-3002"),
      chain,
      ACCOUNT,
    );
    expect(vote?.title).toBe("Record your vote on SIM-REQ-3002");
    expect(refusal(prepared(chain.eas, attest(RESULT_SCHEMA), "SIM-REQ-3002"))).toContain("attest");
  });

  it("refuses what is not this party's call to Orbit Watch on this chain", () => {
    expect(refusal(prepared(chain.escrow, withdraw, null, { chainId: 84532 }))).toContain(
      "chain 84532",
    );
    expect(refusal(prepared(chain.escrow, withdraw, null, { from: OTHER }))).toContain(
      "not from your wallet",
    );
    expect(refusal(prepared(chain.escrow, withdraw, null, { value: "1" }))).toContain("ether");
    expect(refusal(prepared(OTHER, withdraw))).toContain("not one of Orbit Watch's contracts");
    expect(refusal(prepared(chain.escrow, "0xdeadbeef"))).toContain("could not be read");
    const elsewhere = encodeFunctionData({
      abi: tokenAbi,
      functionName: "approve",
      args: [OTHER, 1n],
    });
    expect(refusal(prepared(chain.token.address, elsewhere))).toContain("approve");
    const transfer = encodeFunctionData({
      abi: tokenAbi,
      functionName: "transfer",
      args: [OTHER, 1n],
    });
    expect(refusal(prepared(chain.token.address, transfer))).toContain("transfer");
    expect(refusal({ ...prepared(chain.escrow, withdraw), sign: [] })).toContain("no transaction");
  });

  it("refuses a call about another request than the one shown", () => {
    const reserve = encodeFunctionData({
      abi: escrowAbi,
      functionName: "reserve",
      args: [key("SIM-REQ-3002")],
    });
    expect(
      describePrepared(prepared(chain.escrow, reserve, "SIM-REQ-3002"), chain, ACCOUNT)[0]?.title,
    ).toBe("Reserve SIM-REQ-3002");
    expect(refusal(prepared(chain.escrow, reserve, "SIM-REQ-3001"))).toContain("another request");
    expect(refusal(prepared(chain.escrow, reserve, null))).toContain("another request");
  });
});
