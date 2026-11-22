// A station's passes of a request's object, and the part of each it can see (decisions
// P5-12, D-58). Pure functions, unit tested.

import { formatUtc } from "./format";
import type { Labels } from "./labels";
import { strings } from "./strings";

const s = strings.passes;

/** One pass, as GET /v1/requests/{id}/passes gives it. */
export interface PassView {
  rise: string;
  culmination: string;
  set: string;
  max_elevation_deg: number;
  visible: boolean;
  visible_start: string | null;
  visible_peak: string | null;
  visible_end: string | null;
  visible_max_elevation_deg: number | null;
}

export interface PassList {
  request_id: string;
  window_start: string;
  window_end: string;
  window_cut: boolean;
  min_elevation_deg: number;
  dark_sky_deg: number;
  place: "exact" | "kilometre";
  reference_orbit: Labels["reference_orbit"];
  passes: PassView[];
}

/** "15:44" from an ISO time, for times within a row whose day the rise gives. */
export function clock(iso: string): string {
  return formatUtc(iso).slice(11, 16);
}

/** The cells of a pass's row: rise, highest point, set and the visible part. */
export function passCells(pass: PassView): [string, string, string, string] {
  const visible =
    pass.visible && pass.visible_start && pass.visible_end && pass.visible_peak
      ? s.visiblePart(
          clock(pass.visible_start),
          clock(pass.visible_end),
          pass.visible_max_elevation_deg ?? pass.max_elevation_deg,
          clock(pass.visible_peak),
        )
      : s.notVisible;
  return [
    formatUtc(pass.rise),
    s.highest(clock(pass.culmination), pass.max_elevation_deg),
    clock(pass.set),
    visible,
  ];
}
