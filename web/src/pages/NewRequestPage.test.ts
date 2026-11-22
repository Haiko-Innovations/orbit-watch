import { describe, expect, it } from "vitest";
import { requestSimulated, suggestRequestId, targetSimulated } from "./NewRequestPage";

describe("suggestRequestId", () => {
  it("is a valid request ID with the day and random letters", () => {
    const id = suggestRequestId(new Date("2026-11-13T09:00:00Z"));
    expect(id).toMatch(/^REQ-20261113-[A-Z2-9]{4}$/);
    expect(id).toMatch(/^[A-Za-z0-9._-]{1,64}$/);
  });
});

describe("requestSimulated", () => {
  const real = { norad_id: 99015, name: "TEST", simulated: false };
  const simulated = { norad_id: 339001, name: "SIM-CUBESAT-A", simulated: true };
  const older = { norad_id: 339002, name: "SIM-CUBESAT-B" };
  const targets = { targets: [real, simulated, older], simulated: false };

  it("follows the target, or the whole list from an older service", () => {
    expect(requestSimulated(real, targets, false)).toBe(false);
    expect(requestSimulated(simulated, targets, false)).toBe(true);
    expect(requestSimulated(older, { ...targets, simulated: true }, false)).toBe(true);
    expect(targetSimulated(real, targets)).toBe(false);
  });

  it("is SIMULATED for a real object when simulated stations may observe it", () => {
    expect(requestSimulated(real, targets, true)).toBe(true);
    expect(requestSimulated(simulated, targets, true)).toBe(true);
  });
});
