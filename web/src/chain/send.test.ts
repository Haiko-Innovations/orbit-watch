import { BaseError, encodeErrorResult } from "viem";
import { describe, expect, it } from "vitest";
import { escrowAbi } from "./abis";
import { explainRevert, revertData } from "./send";

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
