import { describe, expect, it } from "vitest";
import { suggestRequestId } from "./NewRequestPage";

describe("suggestRequestId", () => {
  it("is a valid request ID with the day and random letters", () => {
    const id = suggestRequestId(new Date("2026-11-13T09:00:00Z"));
    expect(id).toMatch(/^REQ-20261113-[A-Z2-9]{4}$/);
    expect(id).toMatch(/^[A-Za-z0-9._-]{1,64}$/);
  });
});
