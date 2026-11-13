import { describe, expect, it } from "vitest";
import { ApiError, chainInfo, getJson } from "./api";

function answer(status: number, body: unknown): typeof fetch {
  return async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
}

describe("getJson", () => {
  it("returns the document", async () => {
    expect(await getJson("/v1/health", answer(200, { status: "ok" }))).toEqual({ status: "ok" });
  });

  it("turns a refusal into the API's code and message", async () => {
    const refused = answer(404, { error: { code: "not_found", message: "no such request" } });
    await expect(getJson("/v1/x", refused)).rejects.toMatchObject({
      name: "ApiError",
      code: "not_found",
      message: "no such request",
      status: 404,
    });
  });

  it("explains an answer without the API's error document", async () => {
    await expect(getJson("/v1/x", answer(502, "Bad Gateway"))).rejects.toMatchObject({
      code: "http_error",
      status: 502,
    });
  });

  it("says when the service cannot be reached", async () => {
    const offline: typeof fetch = async () => {
      throw new TypeError("Failed to fetch");
    };
    const error = await getJson("/v1/x", offline).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("unreachable");
  });
});

describe("chainInfo", () => {
  it("is null when the service runs with the points ledger", async () => {
    const ledger = answer(409, { error: { code: "not_on_chain", message: "no chain" } });
    expect(await chainInfo(ledger)).toBeNull();
  });

  it("passes other failures on", async () => {
    const broken = answer(503, { error: { code: "chain_unavailable", message: "node down" } });
    await expect(chainInfo(broken)).rejects.toMatchObject({ code: "chain_unavailable" });
  });
});
