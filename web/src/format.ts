// Formatting of amounts, times and addresses. Pure functions, unit tested.

/** Token units as a decimal amount: 1300000 with 6 decimals is "1.3". */
export function formatUnits(units: number | bigint, decimals: number): string {
  const value = BigInt(units);
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(decimals + 1, "0");
  const whole = digits.slice(0, digits.length - decimals);
  const fraction = digits.slice(digits.length - decimals).replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole}${fraction ? `.${fraction}` : ""}`;
}

/** An amount with its unit: token units on a chain, points with the ledger. */
export function formatAmount(
  units: number | bigint,
  token: { symbol: string; decimals: number } | null,
): string {
  if (token === null) return `${units.toString()} points`;
  return `${formatUnits(units, token.decimals)} ${token.symbol}`;
}

/** An ISO time as "2026-11-01 15:00 UTC". Times are always shown in UTC. */
export function formatUtc(iso: string): string {
  const time = new Date(iso);
  if (Number.isNaN(time.getTime())) return iso;
  return `${time.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

/** "0x1234…abcd" for an address or hash. */
export function shortHex(value: string): string {
  return value.length > 14 ? `${value.slice(0, 6)}…${value.slice(-4)}` : value;
}

/** The explorer page of an address, or null without an explorer (a local chain). */
export function addressLink(explorer: string | null, address: string): string | null {
  return explorer ? `${explorer.replace(/\/$/, "")}/address/${address}` : null;
}
