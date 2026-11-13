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

/** A decimal amount typed by a person, in token units: "1.3" with 6 decimals is 1300000n.
 * Null if it is not a plain non-negative number with at most ``decimals`` decimals. */
export function parseUnits(text: string, decimals: number): bigint | null {
  const match = /^(\d+)(?:\.(\d*))?$/.exec(text.trim());
  if (!match) return null;
  const whole = match[1] ?? "0";
  const fraction = match[2] ?? "";
  if (fraction.length > decimals) return null;
  return BigInt(whole + fraction.padEnd(decimals, "0"));
}

/** The value of an <input type="datetime-local">, read as UTC: "2026-11-01T15:00" is
 * "2026-11-01T15:00:00.000Z". Null if empty or not a time. */
export function utcFromInput(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(value)) return null;
  const time = new Date(`${value}Z`);
  return Number.isNaN(time.getTime()) ? null : time.toISOString();
}

/** An ISO time as the value of an <input type="datetime-local">, in UTC. */
export function inputFromUtc(iso: string): string {
  return new Date(iso).toISOString().slice(0, 16);
}
