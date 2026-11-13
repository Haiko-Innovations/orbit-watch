import type { EIP1193Provider } from "viem";

// Wallets announce themselves to the page (EIP-6963), so several extensions can live side
// by side and the user chooses one (decision P3-03). A page that hears no announcement
// falls back to the one provider an older wallet puts at window.ethereum.

export interface WalletInfo {
  uuid: string;
  name: string;
  icon: string;
  rdns: string;
}

export interface Wallet {
  info: WalletInfo;
  provider: EIP1193Provider;
}

interface Announcement {
  info?: Partial<WalletInfo>;
  provider?: EIP1193Provider;
}

export const LEGACY_UUID = "window.ethereum";

/** An icon is shown only as an image data URL, as EIP-6963 requires (and the CSP allows). */
export function safeIcon(icon: unknown): string {
  return typeof icon === "string" && /^data:image\/(svg\+xml|png|webp|jpeg|gif)[;,]/.test(icon)
    ? icon
    : "";
}

export function readAnnouncement(detail: unknown): Wallet | null {
  const { info, provider } = (detail ?? {}) as Announcement;
  if (!info || !provider || typeof provider.request !== "function") return null;
  if (typeof info.uuid !== "string" || typeof info.name !== "string") return null;
  return {
    info: {
      uuid: info.uuid,
      name: info.name.slice(0, 64),
      icon: safeIcon(info.icon),
      rdns: typeof info.rdns === "string" ? info.rdns : "",
    },
    provider,
  };
}

/** Calls ``changed`` with every wallet found so far; returns the function that stops. */
export function discoverWallets(
  changed: (wallets: Wallet[]) => void,
  target: Window = window,
): () => void {
  const found = new Map<string, Wallet>();
  const report = () => changed([...found.values()]);
  const announced = (event: Event) => {
    const wallet = readAnnouncement((event as CustomEvent).detail);
    if (wallet === null || found.has(wallet.info.uuid)) return;
    found.delete(LEGACY_UUID); // an announcing wallet replaces the old-style one
    found.set(wallet.info.uuid, wallet);
    report();
  };
  target.addEventListener("eip6963:announceProvider", announced);
  target.dispatchEvent(new Event("eip6963:requestProvider"));
  const legacy = (target as Window & { ethereum?: EIP1193Provider }).ethereum;
  const timer = target.setTimeout(() => {
    if (found.size === 0 && legacy && typeof legacy.request === "function") {
      found.set(LEGACY_UUID, {
        info: { uuid: LEGACY_UUID, name: "Browser wallet", icon: "", rdns: "" },
        provider: legacy,
      });
    }
    report();
  }, 300);
  return () => {
    target.removeEventListener("eip6963:announceProvider", announced);
    target.clearTimeout(timer);
  };
}
