import type { Page } from "@playwright/test";
import { BaseError, createWalletClient, type Hex, http, keccak256, toBytes } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { foundry } from "viem/chains";

// A test wallet for the end-to-end tests (decision P3-08). It announces itself to the page
// as an EIP-6963 wallet. Its key stays in the test runner, which signs and sends when the
// page asks; reads go to the local chain, as a real wallet forwards them to its node.
// The keys are LOCAL TEST keys, the same that core/tests/anvil.py derives from a name.

export const CHAIN_PORT = 8591; // the local stack's chain in the end-to-end tests
export const CHAIN_RPC = `http://127.0.0.1:${CHAIN_PORT}`;

export function localTestKey(name: string): Hex {
  return keccak256(toBytes(`orbit-watch local test account|${name}`));
}

interface Options {
  /** Say no to signing messages. */
  decline?: boolean;
  /** Say no to sending transactions. */
  declineSend?: boolean;
  /** Refuse to switch networks. */
  refuseSwitch?: boolean;
  name?: string;
}

type Answer = { result?: unknown; error?: { code: number; message: string; data?: unknown } };

function revertData(error: unknown): Hex | undefined {
  let found: Hex | undefined;
  const look = (value: unknown) => {
    const data = (value as { data?: unknown } | null)?.data;
    if (typeof data === "string" && data.startsWith("0x")) found = data as Hex;
    else if (data && typeof data === "object") look(data);
  };
  if (error instanceof BaseError) {
    error.walk((inner) => {
      look(inner);
      return found !== undefined;
    });
  } else look(error);
  return found;
}

export async function installTestWallet(
  page: Page,
  key: Hex,
  options: Options = {},
): Promise<string> {
  const account = privateKeyToAccount(key);
  const wallet = createWalletClient({ account, chain: foundry, transport: http(CHAIN_RPC) });

  await page.exposeFunction("orbitWatchTestSign", async (raw: Hex): Promise<Answer> => {
    if (options.decline) return { error: { code: 4001, message: "User rejected the request." } };
    return { result: await account.signMessage({ message: { raw } }) };
  });
  await page.exposeFunction(
    "orbitWatchTestSend",
    async (tx: { to: Hex; data?: Hex; value?: Hex }): Promise<Answer> => {
      if (options.declineSend)
        return { error: { code: 4001, message: "User rejected the request." } };
      try {
        const hash = await wallet.sendTransaction({
          to: tx.to,
          data: tx.data ?? "0x",
          value: BigInt(tx.value ?? "0x0"),
        });
        return { result: hash };
      } catch (error) {
        const data = revertData(error);
        const message = error instanceof BaseError ? error.shortMessage : String(error);
        // EIP-1474: 3 is a revert with its data; -32000 any other refusal of the node.
        return { error: { code: data ? 3 : -32000, message, ...(data ? { data } : {}) } };
      }
    },
  );
  await page.exposeFunction(
    "orbitWatchTestRead",
    async (method: string, params: unknown[]): Promise<Answer> => {
      const response = await fetch(CHAIN_RPC, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      });
      return (await response.json()) as Answer;
    },
  );
  await page.addInitScript(
    ({ address, name, refuseSwitch }) => {
      let chainId = 31337;
      const fail = (code: number, message: string, data?: unknown) =>
        Object.assign(new Error(message), { code, data });
      const bridge = window as unknown as Record<string, (...args: unknown[]) => Promise<unknown>>;
      const call = async (fn: string, ...args: unknown[]) => {
        const answer = (await bridge[fn]?.(...args)) as {
          result?: unknown;
          error?: { code: number; message: string; data?: unknown };
        };
        if (answer.error) throw fail(answer.error.code, answer.error.message, answer.error.data);
        return answer.result;
      };
      // The test changes the wallet's network as a user would in the wallet itself.
      (window as unknown as Record<string, unknown>).orbitWatchTestWalletChain = (id: number) => {
        chainId = id;
      };
      const provider = {
        async request({ method, params }: { method: string; params?: unknown[] }) {
          switch (method) {
            case "eth_requestAccounts":
            case "eth_accounts":
              return [address];
            case "eth_chainId":
              return `0x${chainId.toString(16)}`;
            case "wallet_switchEthereumChain":
            case "wallet_addEthereumChain":
              if (refuseSwitch) throw fail(4001, "User rejected the request.");
              chainId = Number.parseInt(
                ((params?.[0] ?? {}) as { chainId?: string }).chainId ?? "0x7a69",
                16,
              );
              return null;
            case "personal_sign":
              return call("orbitWatchTestSign", params?.[0]);
            case "eth_sendTransaction":
              if (chainId !== 31337) throw fail(4901, "The wallet is on another network.");
              return call("orbitWatchTestSend", params?.[0]);
            default:
              return call("orbitWatchTestRead", method, params ?? []);
          }
        },
        on() {},
        removeListener() {},
      };
      const info = {
        uuid: "7c5d1f0e-0000-4000-8000-0000000000aa",
        name,
        icon: "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 8 8'%3E%3Ccircle cx='4' cy='4' r='4' fill='%23888'/%3E%3C/svg%3E",
        rdns: "org.orbit-watch.test-wallet",
      };
      const announce = () =>
        window.dispatchEvent(
          new CustomEvent("eip6963:announceProvider", {
            detail: Object.freeze({ info, provider }),
          }),
        );
      window.addEventListener("eip6963:requestProvider", announce);
      announce();
    },
    {
      address: account.address,
      name: options.name ?? "Test wallet (LOCAL keys)",
      refuseSwitch: options.refuseSwitch ?? false,
    },
  );
  return account.address;
}
