import { describe, expect, it } from "vitest";
import {
  addressLink,
  formatAmount,
  formatUnits,
  formatUtc,
  inputFromUtc,
  parseUnits,
  shortHex,
  utcFromInput,
} from "./format";

describe("formatUnits", () => {
  it("places the decimal point and drops trailing zeros", () => {
    expect(formatUnits(1_300_000, 6)).toBe("1.3");
    expect(formatUnits(100_000, 6)).toBe("0.1");
    expect(formatUnits(1, 6)).toBe("0.000001");
    expect(formatUnits(5_000_000, 6)).toBe("5");
    expect(formatUnits(0, 6)).toBe("0");
    expect(formatUnits(-1_500_000, 6)).toBe("-1.5");
  });

  it("is exact beyond floating point", () => {
    expect(formatUnits(123_456_789_012_345_678_901n, 18)).toBe("123.456789012345678901");
  });
});

describe("formatAmount", () => {
  it("uses the token on a chain and points with the ledger", () => {
    expect(formatAmount(1_000_000, { symbol: "USDC", decimals: 6 })).toBe("1 USDC");
    expect(formatAmount(100, null)).toBe("100 points");
  });
});

describe("formatUtc", () => {
  it("always shows UTC to the minute", () => {
    expect(formatUtc("2026-11-01T15:00:00.000Z")).toBe("2026-11-01 15:00 UTC");
    expect(formatUtc("2026-11-01T17:30:00+02:00")).toBe("2026-11-01 15:30 UTC");
  });

  it("leaves what it cannot read as it is", () => {
    expect(formatUtc("soon")).toBe("soon");
  });
});

describe("addresses", () => {
  it("shortens long hex values", () => {
    expect(shortHex("0xdfeB2255BdB4a3be616c215858B87Eb15E57f4D4")).toBe("0xdfeB…f4D4");
    expect(shortHex("0x1234")).toBe("0x1234");
  });

  it("links to the explorer only when there is one", () => {
    expect(addressLink("https://sepolia.basescan.org", "0xabc")).toBe(
      "https://sepolia.basescan.org/address/0xabc",
    );
    expect(addressLink(null, "0xabc")).toBeNull();
  });
});

describe("parseUnits", () => {
  it("reads what a person types into token units", () => {
    expect(parseUnits("1.3", 6)).toBe(1_300_000n);
    expect(parseUnits("0.1", 6)).toBe(100_000n);
    expect(parseUnits(" 5 ", 6)).toBe(5_000_000n);
    expect(parseUnits("0", 6)).toBe(0n);
    expect(parseUnits("2.", 6)).toBe(2_000_000n);
  });

  it("refuses what is not a plain amount, or finer than the token", () => {
    for (const text of ["", "-1", "1e3", "1,5", "abc", "1.0000001", ".5"]) {
      expect(parseUnits(text, 6), text).toBeNull();
    }
  });
});

describe("UTC inputs", () => {
  it("reads a datetime-local value as UTC and back", () => {
    expect(utcFromInput("2026-11-01T15:00")).toBe("2026-11-01T15:00:00.000Z");
    expect(inputFromUtc("2026-11-01T15:00:00.000Z")).toBe("2026-11-01T15:00");
    expect(utcFromInput("")).toBeNull();
    expect(utcFromInput("tomorrow")).toBeNull();
  });
});
