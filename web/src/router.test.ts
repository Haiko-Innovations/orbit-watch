import { describe, expect, it } from "vitest";
import { parseHash, paths } from "./router";

describe("parseHash", () => {
  it("knows the pages", () => {
    expect(parseHash("")).toEqual({ page: "network" });
    expect(parseHash("#/")).toEqual({ page: "network" });
    expect(parseHash(paths.openRequests)).toEqual({ page: "open-requests" });
    expect(parseHash("#/requests/")).toEqual({ page: "open-requests" });
  });

  it("reads a request's page", () => {
    expect(parseHash("#/requests/SIM-REQ-3001")).toEqual({ page: "request", id: "SIM-REQ-3001" });
    expect(parseHash(paths.request("REQ-20261113-AB2C"))).toEqual({
      page: "request",
      id: "REQ-20261113-AB2C",
    });
    expect(parseHash("#/requests/bad%20id")).toEqual({ page: "not-found" });
    expect(parseHash("#/my-requests")).toEqual({ page: "my-requests" });
    expect(parseHash("#/new-request")).toEqual({ page: "new-request" });
  });

  it("calls everything else not found", () => {
    expect(parseHash("#/admin")).toEqual({ page: "not-found" });
    expect(parseHash("#main")).toEqual({ page: "not-found" });
  });
});
