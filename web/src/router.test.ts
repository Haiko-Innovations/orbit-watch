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
    expect(parseHash("#/tasks")).toEqual({ page: "tasks" });
    expect(parseHash(paths.task("task-eca9bfa388a8343d8f6e"))).toEqual({
      page: "task",
      id: "task-eca9bfa388a8343d8f6e",
    });
  });

  it("knows the administrator view and the public pages (step 3.7)", () => {
    expect(parseHash(paths.admin)).toEqual({ page: "admin" });
    expect(parseHash(paths.attestations)).toEqual({ page: "attestations" });
    expect(parseHash(paths.quality)).toEqual({ page: "quality" });
  });

  it("calls everything else not found", () => {
    expect(parseHash("#/admin/keys")).toEqual({ page: "not-found" });
    expect(parseHash("#main")).toEqual({ page: "not-found" });
  });
});
