import { BaseError, type EIP1193Provider, encodeErrorResult } from "viem";
import { describe, expect, it } from "vitest";
import { NOT_ALLOWED } from "../wallet/wallet";
import { escrowAbi } from "./abis";
import type { Described } from "./describe";
import { explainRevert, revertData, sendWithWallet } from "./send";

const nothing = encodeErrorResult({ abi: escrowAbi, errorName: "NothingToWithdraw" });

describe("explainRevert", () => {
  it("names the escrow's own error, however deep the wallet put it", () => {
    expect(revertData({ code: 3, data: nothing })).toBe(nothing);
    const wrapped = new BaseError("Execution reverted", {
      cause: Object.assign(new Error("execution reverted"), { code: 3, data: { data: nothing } }),
    });
    expect(revertData(wrapped)).toBe(nothing);
    expect(explainRevert(wrapped)).toContain("nothing to withdraw any more");
  });

  it("still says the chain refused when the reason is unknown", () => {
    expect(explainRevert({ code: 3, data: "0x12345678" })).toBe(
      "The chain refuses this transaction, so it was not sent.",
    );
    expect(explainRevert(new BaseError("execution reverted"))).toBe(
      "The chain refuses this transaction, so it was not sent.",
    );
  });

  it("is not a revert when nothing says so", () => {
    expect(explainRevert(new Error("network down"))).toBeNull();
  });
});

describe("sendWithWallet where the wallet has not allowed the account", () => {
  // MetaMask since 13.55.0: https://github.com/MetaMask/metamask-extension/issues/47773
  const ACCOUNT = "0x4803e651A89F3160Ab9b82Db7a8f9Ed25269AC62";
  const HASH = `0x${"12".repeat(32)}`;
  const described = {
    title: "Withdraw",
    detail: null,
    contract: "Orbit Watch escrow",
    to: "0x00000000000000000000000000000000000000e5",
    functionName: "withdraw",
    transaction: {
      chainId: 31337,
      to: "0x00000000000000000000000000000000000000e5",
      data: "0x3ccfd60b",
    },
  } as unknown as Described;

  function wallet(fixedByReconnecting: boolean) {
    const asked: string[] = [];
    let revoked = false;
    let allowed = false;
    const provider = {
      async request({ method }: { method: string }) {
        asked.push(method);
        switch (method) {
          case "eth_chainId":
            return "0x7a69";
          case "wallet_revokePermissions":
            revoked = true;
            return null;
          case "eth_requestAccounts":
            if (revoked && fixedByReconnecting) allowed = true;
            return [ACCOUNT];
          case "eth_sendTransaction":
            if (!allowed) throw Object.assign(new Error("not authorized"), { code: 4100 });
            return HASH;
          default:
            throw Object.assign(new Error(`${method} unsupported`), { code: 4200 });
        }
      },
      on() {},
      removeListener() {},
    } as unknown as EIP1193Provider;
    return { provider, asked };
  }

  it("connects the site again, then sends", async () => {
    const { provider, asked } = wallet(true);
    expect(await sendWithWallet(provider, ACCOUNT, described)).toBe(HASH);
    expect(asked.filter((method) => method === "eth_sendTransaction")).toHaveLength(2);
    expect(asked).toContain("wallet_revokePermissions");
  });

  it("says what to do when connecting again does not help", async () => {
    const { provider, asked } = wallet(false);
    await expect(sendWithWallet(provider, ACCOUNT, described)).rejects.toMatchObject({
      code: "not_allowed",
      message: NOT_ALLOWED,
    });
    expect(asked.filter((method) => method === "eth_sendTransaction")).toHaveLength(2);
  });
});
