import { createDecipheriv, scryptSync } from "node:crypto";
import { readFileSync } from "node:fs";
import { concatHex, type Hex, keccak256 } from "viem";
import { privateKeyToAccount } from "viem/accounts";

// Encrypted keystores (Web3 Secret Storage version 3, scrypt and AES-128-CTR), as
// `orbit-watch` and eth_account write them. The phase 3 demo opens its parties' testnet
// keystores here, in the test runner: the key goes neither to the page nor to the service,
// and nothing prints it.

interface Keystore {
  address?: string;
  version: number;
  crypto: {
    cipher: string;
    ciphertext: string;
    cipherparams: { iv: string };
    kdf: string;
    kdfparams: { dklen: number; n: number; r: number; p: number; salt: string };
    mac: string;
  };
}

export function openKeystore(path: string, password: string): Hex {
  const store = JSON.parse(readFileSync(path, "utf8")) as Keystore;
  const { crypto } = store;
  if (store.version !== 3 || crypto.kdf !== "scrypt" || crypto.cipher !== "aes-128-ctr") {
    throw new Error(`${path}: not a scrypt / aes-128-ctr keystore of version 3`);
  }
  const { dklen, n, r, p, salt } = crypto.kdfparams;
  const derived = scryptSync(password, Buffer.from(salt, "hex"), dklen, {
    N: n,
    r,
    p,
    maxmem: 256 * n * r + 1024 * 1024,
  });
  const ciphertext = Buffer.from(crypto.ciphertext, "hex");
  const mac = keccak256(
    concatHex([`0x${derived.subarray(16, 32).toString("hex")}`, `0x${crypto.ciphertext}`]),
  );
  if (mac.slice(2) !== crypto.mac.toLowerCase()) {
    throw new Error(`${path}: wrong password or a damaged keystore`);
  }
  const decipher = createDecipheriv(
    "aes-128-ctr",
    derived.subarray(0, 16),
    Buffer.from(crypto.cipherparams.iv, "hex"),
  );
  const key =
    `0x${Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("hex")}` as Hex;
  if (
    store.address &&
    privateKeyToAccount(key).address.toLowerCase().slice(2) !==
      store.address.toLowerCase().replace(/^0x/, "")
  ) {
    throw new Error(`${path}: the key does not belong to the keystore's address`);
  }
  return key;
}
