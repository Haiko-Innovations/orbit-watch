import { describe, expect, it, vi } from "vitest";
import { discoverWallets, LEGACY_UUID, readAnnouncement, safeIcon, type Wallet } from "./discovery";

const provider = { request: async () => null, on: () => {}, removeListener: () => {} };

/** A stand-in for window: events, timers, and an optional old-style provider. */
function fakeWindow(legacy?: unknown) {
  const target = new EventTarget() as EventTarget & Record<string, unknown>;
  target.setTimeout = setTimeout;
  target.clearTimeout = clearTimeout;
  if (legacy) target.ethereum = legacy;
  return target as unknown as Window;
}

function announce(target: Window, uuid: string, name: string, icon = "data:image/svg+xml,<svg/>") {
  target.dispatchEvent(
    new CustomEvent("eip6963:announceProvider", {
      detail: { info: { uuid, name, icon, rdns: "org.example" }, provider },
    }),
  );
}

describe("readAnnouncement", () => {
  it("takes a well-formed announcement", () => {
    const wallet = readAnnouncement({
      info: { uuid: "u", name: "W", icon: "", rdns: "x" },
      provider,
    });
    expect(wallet?.info).toEqual({ uuid: "u", name: "W", icon: "", rdns: "x" });
  });

  it("ignores announcements without a provider or an id", () => {
    expect(readAnnouncement({ info: { uuid: "u", name: "W" } })).toBeNull();
    expect(readAnnouncement({ info: { name: "W" }, provider })).toBeNull();
    expect(readAnnouncement(null)).toBeNull();
  });
});

describe("safeIcon", () => {
  it("shows only image data URLs", () => {
    expect(safeIcon("data:image/png;base64,AAAA")).toBe("data:image/png;base64,AAAA");
    expect(safeIcon("https://tracker.example/icon.png")).toBe("");
    expect(safeIcon("javascript:alert(1)")).toBe("");
    expect(safeIcon("data:text/html,<script>")).toBe("");
  });
});

describe("discoverWallets", () => {
  it("collects every wallet that answers, once each", () => {
    const target = fakeWindow();
    target.addEventListener("eip6963:requestProvider", () => {
      announce(target, "a", "Alpha");
      announce(target, "b", "Beta");
      announce(target, "a", "Alpha again");
    });
    const seen: Wallet[][] = [];
    const stop = discoverWallets((wallets) => seen.push(wallets), target);
    expect(seen.at(-1)?.map((w) => w.info.name)).toEqual(["Alpha", "Beta"]);
    stop();
  });

  it("falls back to window.ethereum when no wallet announces itself", () => {
    vi.useFakeTimers();
    const target = fakeWindow(provider);
    const seen: Wallet[][] = [];
    const stop = discoverWallets((wallets) => seen.push(wallets), target);
    vi.advanceTimersByTime(300);
    expect(seen.at(-1)?.map((w) => w.info.uuid)).toEqual([LEGACY_UUID]);
    stop();
    vi.useRealTimers();
  });

  it("reports an empty list when there is no wallet at all", () => {
    vi.useFakeTimers();
    const seen: Wallet[][] = [];
    const stop = discoverWallets((wallets) => seen.push(wallets), fakeWindow());
    vi.advanceTimersByTime(300);
    expect(seen).toEqual([[]]);
    stop();
    vi.useRealTimers();
  });
});
