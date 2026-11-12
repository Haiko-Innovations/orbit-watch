# Phase 2 summary

**English** · [Suomi](phase-2-summary.fi.md)

Phase 2 (monetary settlement on a testnet) is complete as **version 0.3.0**.
This is the end-of-phase summary the [plan](plan.md#8-deliverables) asks for.

> **Testnet only, no real value.** Everything on chain runs on Base Sepolia
> with Circle's testnet USDC, which "has no financial value". All stations,
> observations, requests and reviewers are SIMULATED.

## What works

- **Escrow contract** on Base Sepolia: one non-upgradeable contract holds each
  request's deposit, locked split, terms hash and deadlines. No owner and no
  administrator; money leaves only by settlement rules 1.0, credited and then
  withdrawn by each party ([escrow.md](escrow.md)).
- **Attestations**: the automated result and every reviewer vote are EAS
  attestations with two schemas whose resolver is the escrow, so an attestation
  the rules refuse never exists. Each round's three reviewers are chosen on
  chain by a formula nobody can steer ([attestations.md](attestations.md)).
- **Governance**: the reviewer registry belongs to a 48-hour public timelock
  whose only proposer is a Safe 2-of-3
  ([who can change what](../contracts/README.md#privileges-who-can-change-what)).
- **The service on the chain**: every party signs its own transactions with
  its own wallet or encrypted keystore, from the command line or another
  wallet; the service holds only the verifier key and follows the escrow's
  events, which decide rounds and payments. Pending, confirmed and failed
  transactions are shown apart with explorer links
  ([chain-service.md](chain-service.md)).
- **The deployment** on Base Sepolia from a documented, tested script with
  verified sources, faucet instructions and who holds which key
  ([base-sepolia.md](base-sepolia.md)).
- **The phase 2 demo**: the five requests of the phase 1 demo, on Base
  Sepolia, each party with its own wallet
  ([`examples/phase2/transcript.md`](../examples/phase2/transcript.md)).

### Completion criteria

| Criterion from the plan | Status |
|---|---|
| 1. The system starts with the documented instructions | ✅ [base-sepolia.md](base-sepolia.md): the contracts were deployed and the service run from these instructions |
| 2. Different parties act with different wallets | ✅ the demo: a requester, four stations, reviewers and the verifier, each with its own key |
| 3. A request can be created and funded | ✅ funded by `approve` and `fund` from the requester's wallet |
| 4. An observer can reserve a request and deliver a simulated dataset with the CLI | ✅ `orbit-watch reserve` and `orbit-watch submit`, signed with the station's keystore |
| 5. Automated verification, the challenge period and, through a challenge, the reviewer round work, and the results appear as EAS attestations | ✅ results and votes in the demo's attestation table, on EAS Scan |
| 6. Rewards of an accepted request move as real testnet token transfers | ✅ the observer reward and the review rewards are withdrawn as USDC transfers |
| 7. Rejection, deadline expiry, dispute and refund work | ✅ all in the demo, and in the scenario suite on chain |
| 8. Explorer links are shown | ✅ every transaction in the API, the command line and the transcript |
| 9. An unauthorised party cannot approve work or withdraw a deposit, tested | ✅ contract tests, service tests through the API and on chain, and the demo's checks |
| 10. A retry never pays twice, tested | ✅ contract tests, service tests, and the demo's checks |

The contracts are tested with Foundry (unit, scenario, fuzz and invariant
tests that every deposit is paid out or refunded: deposit = rewards +
refunds), and the Python side on a local Anvil chain in CI, including the
deployment script and this demo.

## What is simulated, and what is a testnet

- All stations, observations, requests and reviewers. Every simulated document
  says so itself.
- The money is Circle's testnet USDC on Base Sepolia, of no value, from faucets.
- **One maintainer holds every key on the testnet** (the Safe signers, the
  verifier and the simulated parties), so the Safe 2-of-3 separates keys, not
  people ([D-24](decisions.md#d-24-the-base-sepolia-deployment)).
- The service runs locally; only the contracts and attestations are public
  ([P2-11](decisions.md#p2-11-phase-2-has-no-public-deployment)).

## How to run it

The demo needs a running service on Base Sepolia and every party's keystore
with a little testnet ETH, and the requester's with testnet USDC
([base-sepolia.md](base-sepolia.md#testnet-eth-and-usdc-faucets)):

```sh
pip install "orbit-watch[api,evm] @ git+https://github.com/Haiko-Innovations/orbit-watch.git@v0.3.0#subdirectory=core"
orbit-watch keys create --dir ./ow-demo --role admin --party admin:me > admin.key
orbit-watch serve --dir ./ow-demo --network base-sepolia \
  --verifier-keystore … --verifier-password-file …            # in another terminal
ORBIT_WATCH_KEY=$(cat admin.key) orbit-watch demo --phase 2 \
  --wallets ~/secrets/orbit-watch/sim --password-file ~/secrets/orbit-watch/password \
  --id-prefix SIM-REQ-300                                      # new IDs for a new run
```

The service's verifier key must be the escrow's, so on the deployed escrow
only its maintainer can run the service; anyone can deploy their own escrow
([base-sepolia.md](base-sepolia.md#deploying-maintainers)) or run the same
demo on a local chain (`core/tests/test_phase2_demo.py`). The deadlines are
minutes long, and a run takes about half an hour.

## Open problems for the next phase

- **Separate people for the keys**: the Safe's three signers, and the verifier
  key away from the maintainer's machine, before anything but a testnet.
- **Calibration on chain**: a reviewer can tell a calibration task from a real
  one, because only a real vote is a public attestation (D-23).
- **Request IDs can be funded first by someone else**; the service shows it as
  a conflict, and the requester needs a new ID. A per-requester key would fix it
  in a new escrow version.
- **No background worker**: the service settles when a party reports a
  transaction or an admin calls `tick`; reorganisations are not handled.
- **Bonds** for reservations, challenges and reviewers, and **personal data**
  (station coordinates in public data), as after phase 1.
- **Phase 3**: the web application, with wallets in the browser and a public
  deployment of the service (TLS, rate limits, key rotation, operations).
- **A real IOD example** of a civilian object, shared with permission
  ([#8](https://github.com/Haiko-Innovations/orbit-watch/issues/8)).
