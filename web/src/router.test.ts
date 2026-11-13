import { describe, expect, it } from "vitest";
import { parseHash, paths } from "./router";

describe("parseHash", () => {
  it("knows the pages", () => {
    expect(parseHash("")).toEqual({ page: "network" });
    expect(parseHash("#/")).toEqual({ page: "network" });
    expect(parseHash(paths.openRequests)).toEqual({ page: "open-requests" });
    expect(parseHash("#/requests/")).toEqual({ page: "open-requests" });
  });

  it("calls everything else not found", () => {
    expect(parseHash("#/admin")).toEqual({ page: "not-found" });
    expect(parseHash("#main")).toEqual({ page: "not-found" });
  });
});
