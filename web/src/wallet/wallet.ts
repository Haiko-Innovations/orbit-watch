import {
  type Address,
  BaseError,
  type Chain,
  createWalletClient,
  custom,
  type EIP1193Provider,
  getAddress,
} from "viem";
import { baseSepolia, foundry } from "viem/chains";
import { parseSiweMessage, validateSiweMessage } from "viem/siwe";

// The browser's part of the chain is small (decision P3-03): connect, switch to the
// service's chain, and sign. Keys never leave the wallet; the service sees signatures only.

/** The chains a service may run on, with the settings a wallet needs to add them. The local
 * stack runs its chain on port 8545, where viem's `foundry` chain points. */
export const CHAINS: Record<number, Chain> = {
  [baseSepolia.id]: baseSepolia,
  [foundry.id]: foundry,
};

export class WalletError extends Error {
  readonly code: "declined" | "no_account" | "wrong_chain" | "wrong_message" | "failed";

  constructor(code: WalletError["code"], message: string) {
    super(message);
    this.name = "WalletError";
    this.code = code;
  }
}

/** Whether the user said no in the wallet (EIP-1193 error 4001). */
export function isUserRejection(error: unknown): boolean {
  if (error instanceof BaseError) {
    return error.walk((e) => (e as { code?: unknown }).code === 4001) !== null;
  }
  return (error as { code?: unknown } | null)?.code === 4001;
}

function client(provider: EIP1193Provider) {
  return createWalletClient({ transport: custom(provider) });
}

async function guarded<T>(work: () => Promise<T>, failed: string): Promise<T> {
  try {
    return await work();
  } catch (error) {
    if (error instanceof WalletError) throw error;
    if (isUserRejection(error)) throw new WalletError("declined", "You declined in your wallet.");
    const detail = error instanceof BaseError ? error.shortMessage : String(error);
    throw new WalletError("failed", `${failed}: ${detail}`);
  }
}

export async function connect(provider: EIP1193Provider): Promise<Address> {
  return guarded(async () => {
    const [address] = await client(provider).requestAddresses();
    if (!address) throw new WalletError("no_account", "The wallet gave no account.");
    return getAddress(address);
  }, "The wallet did not connect");
}

/** Asks the wallet to use ``chainId``, adding the chain first if the wallet lacks it. */
export async function switchToChain(provider: EIP1193Provider, chainId: number): Promise<void> {
  const chain = CHAINS[chainId];
  if (!chain) throw new WalletError("wrong_chain", `Chain ${chainId} is not one Orbit Watch uses.`);
  await guarded(async () => {
    const wallet = client(provider);
    if ((await wallet.getChainId()) === chainId) return;
    try {
      await wallet.switchChain({ id: chainId });
    } catch (error) {
      if (isUserRejection(error)) throw error;
      // 4902: the wallet does not know the chain yet.
      await wallet.addChain({ chain });
      await wallet.switchChain({ id: chainId });
    }
  }, `The wallet did not switch to ${chain.name}`);
}

/** Signs a sign-in message after checking that it is for this page and this account. */
export async function signSignIn(
  provider: EIP1193Provider,
  address: Address,
  message: string,
  page: { host: string; protocol: string } = window.location,
  now: Date = new Date(),
): Promise<string> {
  const parsed = parseSiweMessage(message);
  const ours = validateSiweMessage({
    message: parsed,
    address,
    domain: page.host,
    scheme: page.protocol.replace(/:$/, ""),
    time: now,
  });
  if (!ours) {
    throw new WalletError(
      "wrong_message",
      "The service asked to sign a message for another site or account, so nothing was signed.",
    );
  }
  return guarded(
    () => client(provider).signMessage({ account: address, message }),
    "The wallet did not sign",
  );
}
