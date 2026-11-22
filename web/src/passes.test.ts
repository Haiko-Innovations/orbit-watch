import { describe, expect, it } from "vitest";
import { clock, type PassView, passCells } from "./passes";

const visible: PassView = {
  rise: "2026-11-01T15:39:20.000Z",
  culmination: "2026-11-01T15:44:50.000Z",
  set: "2026-11-01T15:50:30.000Z",
  max_elevation_deg: 29.4,
  visible: true,
  visible_start: "2026-11-01T15:39:20.000Z",
  visible_peak: "2026-11-01T15:44:50.000Z",
  visible_end: "2026-11-01T15:50:30.000Z",
  visible_max_elevation_deg: 29.4,
};

describe("passCells", () => {
  it("gives a visible pass's times and its visible part", () => {
    expect(passCells(visible)).toEqual([
      "2026-11-01 15:39 UTC",
      "15:44, 29°",
      "15:50",
      "15:39–15:50, highest 29° at 15:44",
    ]);
  });

  it("says why a pass is not visible", () => {
    const shadow = {
      ...visible,
      visible: false,
      visible_start: null,
      visible_peak: null,
      visible_end: null,
      visible_max_elevation_deg: null,
    };
    expect(passCells(shadow)[3]).toBe("not visible: in the Earth's shadow or in daylight");
  });
});

describe("clock", () => {
  it("is the time of day in UTC", () => {
    expect(clock("2026-11-01T17:18:59.000Z")).toBe("17:18");
  });
});
