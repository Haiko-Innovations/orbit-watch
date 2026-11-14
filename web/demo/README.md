# The phase 3 demo on Base Sepolia

> **Base Sepolia testnet, no real value.** Every station, observation, request
> and reviewer is SIMULATED.

[`base-sepolia.demo.ts`](base-sepolia.demo.ts) runs the whole chain in the
browser on Base Sepolia, every role in its own browser with its own wallet, and
writes [`examples/phase3`](../../examples/phase3)
([D-33](../../docs/decisions.md#d-33-the-phase-3-demo-and-the-accessibility-review)).
It is for the maintainer, who holds the testnet keystores (D-24), and is not
part of CI.

```sh
cd web && npm run build
ORBIT_WATCH_SECRETS=~/secrets/orbit-watch ORBIT_WATCH_DEMO_DIR=~/ow-phase3-demo \
  ORBIT_WATCH_DEMO_REQUEST=SIM-REQ-3805 npm run demo:base-sepolia
```

- **Every run needs a new request ID**, because the escrow is shared.
- **[`serve.sh`](serve.sh) starts the service** on the deployment with the
  verifier's keystore. Its PostgreSQL is `ORBIT_WATCH_DATABASE_URL`, or else
  a LOCAL one in Docker, removed when the demo ends.
- **[`keystore.ts`](keystore.ts) opens each party's encrypted keystore** in the
  test runner. The key reaches neither the page nor the service, and nothing
  prints it.
- **Each party needs a little testnet ETH**, and the requester testnet USDC
  ([faucets](../../docs/base-sepolia.md#testnet-eth-and-usdc-faucets)).
- **Videos** of every role's browser go to `ORBIT_WATCH_DEMO_DIR/videos`.
