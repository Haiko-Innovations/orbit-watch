import type { EIP1193Provider } from "viem";
import { describe, expect, it } from "vitest";
import { connect, isUserRejection, signSignIn, switchToChain, WalletError } from "./wallet";

const ADDRESS = "0x4803e651A89F3160Ab9b82Db7a8f9Ed25269AC62";
const SIGNATURE = `0x${"ab".repeat(65)}`;

/** A wallet that answers from a table and records what it was asked. */
function fakeWallet(answers: Record<string, (params: unknown) => unknown>) {
  const asked: string[] = [];
  const provider = {
    async request({ method, params }: { method: string; params?: unknown }) {
      asked.push(method);
      const answer = answers[method];
      if (!answer) throw Object.assign(new Error(`${method} unsupported`), { code: 4200 });
      return answer(params);
    },
    on() {},
    removeListener() {},
  } as unknown as EIP1193Provider;
  return { provider, asked };
}

function message(origin: string, address = ADDRESS, expires = "2026-11-13T09:05:00.000Z") {
  return [
    `${origin} wants you to sign in with your Ethereum account:`,
    address,
    "",
    "Sign in to Orbit Watch as station:SIM-ESPOO. Testnet only, no real value. Signing sends no transaction.",
    "",
    `URI: ${origin}/`,
    "Version: 1",
    "Chain ID: 31337",
    "Nonce: abcdefgh12345678x",
    "Issued At: 2026-11-13T09:00:00.000Z",
    `Expiration Time: ${expires}`,
  ].join("\n");
}

const page = { host: "127.0.0.1:8787", protocol: "http:" };
const now = new Date("2026-11-13T09:01:00Z");

describe("isUserRejection", () => {
  it("knows EIP-1193's 4001", () => {
    expect(isUserRejection({ code: 4001 })).toBe(true);
    expect(isUserRejection({ code: 4200 })).toBe(false);
    expect(isUserRejection(null)).toBe(false);
  });
});

describe("connect", () => {
  it("returns the first account, checksummed", async () => {
    const { provider } = fakeWallet({ eth_requestAccounts: () => [ADDRESS.toLowerCase()] });
    expect(await connect(provider)).toBe(ADDRESS);
  });

  it("says when the user declines", async () => {
    const { provider } = fakeWallet({
      eth_requestAccounts: () => {
        throw Object.assign(new Error("User rejected the request."), { code: 4001 });
      },
    });
    await expect(connect(provider)).rejects.toMatchObject({ code: "declined" });
  });
});

describe("switchToChain", () => {
  it("does nothing on the right chain", async () => {
    const { provider, asked } = fakeWallet({ eth_chainId: () => "0x7a69" });
    await switchToChain(provider, 31337);
    expect(asked).toEqual(["eth_chainId"]);
  });

  it("adds a chain the wallet does not know, then switches", async () => {
    let known = false;
    const { provider, asked } = fakeWallet({
      eth_chainId: () => "0x1",
      wallet_switchEthereumChain: () => {
        if (!known) throw Object.assign(new Error("Unrecognized chain"), { code: 4902 });
        return null;
      },
      wallet_addEthereumChain: () => {
        known = true;
        return null;
      },
    });
    await switchToChain(provider, 84532);
    expect(asked).toEqual([
      "eth_chainId",
      "wallet_switchEthereumChain",
      "wallet_addEthereumChain",
      "wallet_switchEthereumChain",
    ]);
  });

  it("refuses chains Orbit Watch does not use", async () => {
    const { provider } = fakeWallet({});
    await expect(switchToChain(provider, 1)).rejects.toBeInstanceOf(WalletError);
  });
});

describe("signSignIn", () => {
  it("signs a message for this page and this account", async () => {
    const { provider, asked } = fakeWallet({ personal_sign: () => SIGNATURE });
    const signed = await signSignIn(provider, ADDRESS, message("http://127.0.0.1:8787"), page, now);
    expect(signed).toBe(SIGNATURE);
    expect(asked).toEqual(["personal_sign"]);
  });

  it("refuses, without asking the wallet, a message for another site", async () => {
    const { provider, asked } = fakeWallet({ personal_sign: () => SIGNATURE });
    for (const other of [
      message("https://evil.example"),
      message("https://127.0.0.1:8787"),
      message("http://127.0.0.1:8787", "0x0000000000000000000000000000000000000001"),
      message("http://127.0.0.1:8787", ADDRESS, "2026-11-13T09:00:30.000Z"),
    ]) {
      await expect(signSignIn(provider, ADDRESS, other, page, now)).rejects.toMatchObject({
        code: "wrong_message",
      });
    }
    expect(asked).toEqual([]);
  });
});
