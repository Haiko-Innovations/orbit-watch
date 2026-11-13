import type { Wallet } from "./discovery";

// The wallet the party signed in with, kept in memory only: nothing about wallets is
// stored in the browser. After a reload the page asks again which wallet to use.

let current: Wallet | null = null;

export function rememberWallet(wallet: Wallet): void {
  current = wallet;
}

export function rememberedWallet(): Wallet | null {
  return current;
}
