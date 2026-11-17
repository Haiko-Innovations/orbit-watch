import type { EIP1193Provider } from "viem";
import { describe, expect, it } from "vitest";
import {
  connect,
  isUnauthorized,
  isUserRejection,
  NOT_ALLOWED,
  signSignIn,
  switchToChain,
  WalletError,
} from "./wallet";

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

/** MetaMask since 13.55.0 (issue #47773): a network the site added has no accounts permitted,
 * so signing there fails with 4100 until the site connects again. */
function walletWithoutAccountOnNetwork({
  revoke = true,
  fixedBy = "reconnect",
  accounts = [ADDRESS],
}: {
  revoke?: boolean;
  fixedBy?: "reconnect" | "nothing";
  accounts?: string[];
} = {}) {
  let revoked = false;
  let allowed = false;
  const unauthorized = () =>
    Object.assign(new Error("The requested account and/or method has not been authorized."), {
      code: 4100,
    });
  return fakeWallet({
    personal_sign: () => {
      if (!allowed) throw unauthorized();
      return SIGNATURE;
    },
    ...(revoke
      ? {
          wallet_revokePermissions: () => {
            revoked = true;
            return null;
          },
        }
      : {}),
    eth_requestAccounts: () => {
      if (revoked && fixedBy === "reconnect") allowed = true;
      return accounts;
    },
    eth_chainId: () => "0x7a69",
  });
}

describe("isUnauthorized", () => {
  it("knows EIP-1193's 4100", () => {
    expect(isUnauthorized({ code: 4100 })).toBe(true);
    expect(isUnauthorized({ code: 4001 })).toBe(false);
    expect(isUnauthorized(null)).toBe(false);
  });
});

describe("signing where the wallet has not allowed the account", () => {
  const signed = message("http://127.0.0.1:8787");

  it("connects the site again, then signs", async () => {
    const { provider, asked } = walletWithoutAccountOnNetwork();
    expect(await signSignIn(provider, ADDRESS, signed, page, now)).toBe(SIGNATURE);
    expect(asked).toEqual([
      "personal_sign",
      "wallet_revokePermissions",
      "eth_requestAccounts",
      "eth_chainId",
      "personal_sign",
    ]);
  });

  it("says what to do when connecting again does not help", async () => {
    const { provider, asked } = walletWithoutAccountOnNetwork({
      revoke: false,
      fixedBy: "nothing",
    });
    const refused = signSignIn(provider, ADDRESS, signed, page, now);
    await expect(refused).rejects.toBeInstanceOf(WalletError);
    await expect(refused).rejects.toMatchObject({ code: "not_allowed", message: NOT_ALLOWED });
    expect(asked.filter((method) => method === "personal_sign")).toHaveLength(2); // once more only
  });

  it("signs nothing if the wallet comes back without the account", async () => {
    const other = "0x0000000000000000000000000000000000000001";
    const { provider, asked } = walletWithoutAccountOnNetwork({ accounts: [other] });
    await expect(signSignIn(provider, ADDRESS, signed, page, now)).rejects.toMatchObject({
      code: "wrong_account",
    });
    expect(asked.filter((method) => method === "personal_sign")).toHaveLength(1);
  });
});
