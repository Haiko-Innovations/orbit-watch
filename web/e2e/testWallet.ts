import type { Page } from "@playwright/test";
import { type Hex, keccak256, toBytes } from "viem";
import { privateKeyToAccount } from "viem/accounts";

// A test wallet for the end-to-end tests (decision P3-08). It announces itself to the page
// as an EIP-6963 wallet; its key stays in the test runner, which signs when the page asks.
// The keys are LOCAL TEST keys, the same that core/tests/anvil.py derives from a name.

export function localTestKey(name: string): Hex {
  return keccak256(toBytes(`orbit-watch local test account|${name}`));
}

export async function installTestWallet(
  page: Page,
  key: Hex,
  options: { decline?: boolean; name?: string } = {},
): Promise<string> {
  const account = privateKeyToAccount(key);
  await page.exposeFunction("orbitWatchTestSign", async (raw: Hex) => {
    if (options.decline) return { declined: true };
    return { signature: await account.signMessage({ message: { raw } }) };
  });
  await page.addInitScript(
    ({ address, name }) => {
      let chainId = 31337;
      const fail = (code: number, message: string) => Object.assign(new Error(message), { code });
      const provider = {
        async request({ method, params }: { method: string; params?: unknown[] }) {
          switch (method) {
            case "eth_requestAccounts":
            case "eth_accounts":
              return [address];
            case "eth_chainId":
              return `0x${chainId.toString(16)}`;
            case "wallet_switchEthereumChain":
              chainId = Number.parseInt(
                ((params?.[0] ?? {}) as { chainId?: string }).chainId ?? "0x7a69",
                16,
              );
              return null;
            case "personal_sign": {
              const sign = (window as unknown as Record<string, (raw: string) => Promise<unknown>>)
                .orbitWatchTestSign;
              const answer = (await sign?.(params?.[0] as string)) as {
                signature?: string;
                declined?: boolean;
              };
              if (answer.declined) throw fail(4001, "User rejected the request.");
              return answer.signature;
            }
            default:
              throw fail(4200, `the test wallet does not support ${method}`);
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
    { address: account.address, name: options.name ?? "Test wallet (LOCAL keys)" },
  );
  return account.address;
}
