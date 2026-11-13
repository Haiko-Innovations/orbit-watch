# Orbit Watch on Base Sepolia

Phase 2, step 2.7. Script:
[`contracts/script/DeployOrbitWatch.s.sol`](../contracts/script/DeployOrbitWatch.s.sol).
Decision [D-24](decisions.md#d-24-the-base-sepolia-deployment).

> **Testnet only, no real value.** Base Sepolia is a test network. Its ETH and
> Circle's testnet USDC come free from faucets and "have no financial value,
> and are not backed by real US dollars" (Circle). The request service still
> runs locally; only the contracts and attestations are public
> ([P2-11](decisions.md#p2-11-phase-2-has-no-public-deployment)). The
> reviewers named in the deployment are SIMULATED.

## The deployment

Deployed on 2026-11-12 from commit `07b7d09`, in blocks 57952848 to
57952868. The sources of the three Orbit Watch contracts are verified on
[Sourcify](https://sourcify.dev) (exact match). The deployment cost
0.000036 testnet ETH.

| Contract | Address | |
|---|---|---|
| Escrow (`OrbitWatchEscrow` 1.0.0) | [`0xdfeB2255BdB4a3be616c215858B87Eb15E57f4D4`](https://sepolia.basescan.org/address/0xdfeB2255BdB4a3be616c215858B87Eb15E57f4D4) | no owner; holds deposits, applies the rules |
| Reviewer registry | [`0xE1D3f4b308C781aDcAAF628DDf499d78C7361018`](https://sepolia.basescan.org/address/0xE1D3f4b308C781aDcAAF628DDf499d78C7361018) | owned by the timelock; four SIMULATED reviewers |
| Timelock (OpenZeppelin `TimelockController`) | [`0xc1A5cC62027e309830674D1A7f26B1E4909f5704`](https://sepolia.basescan.org/address/0xc1A5cC62027e309830674D1A7f26B1E4909f5704) | 48 hours; the Safe proposes and cancels, anyone executes |
| Safe 1.4.1, 2 of 3 | [`0xcfB913356bd7D99707CCE6CC08f628B38652E458`](https://sepolia.basescan.org/address/0xcfB913356bd7D99707CCE6CC08f628B38652E458) | also the platform fee recipient |
| Token: Circle's testnet USDC | [`0x036CbD53842c5426634e7929541eC2318f3dCF7e`](https://sepolia.basescan.org/address/0x036CbD53842c5426634e7929541eC2318f3dCF7e) | 6 decimals |
| EAS (predeploy) | [`0x4200000000000000000000000000000000000021`](https://sepolia.basescan.org/address/0x4200000000000000000000000000000000000021) | |
| Verifier (the service's key) | [`0x7eB41156A2B4BC03B8d016A58caF322A0FEdFEDc`](https://sepolia.basescan.org/address/0x7eB41156A2B4BC03B8d016A58caF322A0FEdFEDc) | |

| EAS schema | UID |
|---|---|
| Automated result | `0xf05cee4f7b084bb079503f5cacbbe7813509fbb12a6a7b75b552f8e6f8e2e687` |
| Reviewer vote | `0x01817492ea309c39dd325b79268d4685768afdf9612d51a1376ec58abce44b41` |

The escrow registered both schemas itself, with itself as the resolver and
without revocation ([attestations.md](attestations.md)).

The machine-readable record is
[`contracts/deployments/base-sepolia.json`](../contracts/deployments/base-sepolia.json),
written by the deployment script; the Python package carries the same file,
so `orbit-watch serve --network base-sepolia` finds the escrow by itself. The
settings it was deployed from are in
[`base-sepolia.settings.json`](../contracts/deployments/base-sepolia.settings.json),
and Foundry's log of every transaction is in
[`contracts/broadcast/DeployOrbitWatch.s.sol/84532/`](../contracts/broadcast/DeployOrbitWatch.s.sol/84532).

What can change and who can change it: [contracts/README.md](../contracts/README.md#privileges-who-can-change-what).
In short, nothing in the escrow can change. The reviewer list changes only
through the Safe (two signers) and the timelock (48 hours public), and the
deployer kept no privilege.

## Who holds which key

Orbit Watch has one developer in phase 2, so on the testnet **one maintainer
holds every key** (D-24). Each is a separate key, used only on Base Sepolia,
kept as an encrypted keystore on the machine that runs the service and funded
only from faucets.

| Key | Used for | Privilege |
|---|---|---|
| deployer | sent the deployment; passes faucet ETH on to the other keys | none |
| verifier | the service's key: attests automated results, settles reached outcomes | fixed in the escrow; a new verifier needs a new escrow |
| Safe signers 1–3 | two of them approve a change to the reviewer list | through the timelock only, 48 hours public |
| simulated parties | the SIMULATED requester, station and reviewers of the demos | their own requests, deliveries and votes |

**The 2-of-3 Safe separates keys, not people, on the testnet:** one person can
change the reviewer list, though still publicly and only after 48 hours.
Before anything but a testnet, the three signers must be three people. The
Safe can replace its signers itself, two signers approving, without a new
deployment (a test in
[`DeployOrbitWatch.t.sol`](../contracts/test/DeployOrbitWatch.t.sol) shows it).

If the verifier key were lost, every delivery would expire after its
verification timeout and the requester would get the deposit back; nothing is
locked. If it leaked, someone could attest wrong automated results, which the
requester or the observer can challenge; nobody can take money with it.

## Testnet ETH and USDC (faucets)

Every party needs a little Base Sepolia ETH for gas. The requester also needs
testnet USDC for deposits. Checked on 2026-11-12:

- **ETH:** Base lists its faucets on
  [Get Funds](https://docs.base.org/base-chain/tools/network-faucets). Each
  rate-limits claims, usually to one per 24 hours; the Coinbase Developer
  Platform faucet gives up to 0.1 ETH per 24 hours and needs a sign-in.
  Gas costs very little on Base Sepolia: the whole deployment cost
  0.000036 ETH; in the smoke test below, a party's transaction cost less than
  0.000001 ETH and the verifier's attestation about 0.0000035 ETH.
- **USDC:** [Circle's faucet](https://faucet.circle.com), network
  **Base Sepolia**: 20 USDC per address and network every 2 hours, no
  account, with a reCAPTCHA. The token is
  `0x036CbD53842c5426634e7929541eC2318f3dCF7e`
  ([Circle's list of USDC addresses](https://developers.circle.com/stablecoins/usdc-contract-addresses)).

With several keys of your own, claim ETH once and pass it on, for example
`cast send <address> --value 0.002ether --rpc-url https://sepolia.base.org --keystore <yours>`.

## Taking part

Use the command line as on any chain ([chain-service.md](chain-service.md#the-command-line)),
with your own encrypted keystore. On Base Sepolia, `--rpc` defaults to Base's
public endpoint `https://sepolia.base.org`, which is "free, rate limited, and
best effort" ([Base](https://docs.base.org/network-information)); give your
own provider's endpoint with `--rpc` if it is too slow.

```sh
cast wallet new ~/secrets/orbit-watch alice.json --password   # once; or cast wallet import
export ORBIT_WATCH_KEYSTORE=~/secrets/orbit-watch/alice.json
orbit-watch chain                  # Base Sepolia testnet, no real value; the addresses above
orbit-watch wallet register        # signs the registration message
```

## Smoke test on 2026-11-12

The whole chain once on Base Sepolia, from the command line and with every
party's own keystore, against the service running locally: the SIMULATED
request `SIM-SMOKE-0001` (the example request under a new ID, with a
six-minute challenge period), the observer reward 1 USDC and the review
reward 0.1 USDC.

| Step | Signed by | Transaction |
|---|---|---|
| approve and fund (deposit 1.3 USDC) | requester | [approve](https://sepolia.basescan.org/tx/0x9c86b736d748c8477ce4e6797edf3f4a0cbb751385d83a5fb8ebbbee8ee5cd98), [fund](https://sepolia.basescan.org/tx/0xc75e1ba3d7090ee65f1ee1b4c2f1819af470e064a3acbc523304ce6bd61b3222) |
| reserve | station | [reserve](https://sepolia.basescan.org/tx/0xaecf4f231a0a9b921d00141394f89991f708976a342e3ca88315e21d439105c4) |
| deliver (the file's SHA-256) | station | [deliver](https://sepolia.basescan.org/tx/0x4f6fd9425e1a131a3a50570af9b5f338c0e997b99491b80e0302baf20baf1ba0) |
| automated result `pass` (EAS attestation) | verifier | [attest](https://sepolia.basescan.org/tx/0xe02c06308bbf9167f8305c2cfbc28dc228e5aa7779ab2138c7bd0b9ca8355e62) |
| settle after the challenge period (`admin tick`) | verifier | [settle](https://sepolia.basescan.org/tx/0xbf17ae0b3f37ef1eaca3e1b371b42819d20fee25b370f887d36ceae91b3780c6) |
| withdraw 1 USDC | station | [withdraw](https://sepolia.basescan.org/tx/0x60486134deb1d3c7b79f09d8e0acf7edb6cbe8c0da7eb3184477ba51f14500ad) |
| withdraw the 0.3 USDC refund | requester | [withdraw](https://sepolia.basescan.org/tx/0x43f7263fbef7aff133e5388008e9fec9727453edf9d836dbc10e34cd17034a62) |

Nobody challenged, so the request was accepted: the station got the observer
reward and the requester the unused review rewards back. Rounds with reviewers
come in the phase 2 demo (step 2.8).

## Running the service on Base Sepolia

```sh
orbit-watch serve --dir ./ow-base-sepolia --network base-sepolia \
  --verifier-keystore ~/secrets/orbit-watch/verifier.json \
  --verifier-password-file ~/secrets/orbit-watch/password
```

The verifier key needs a little ETH for gas. Keep the keystore and the
password file outside the repository and readable only by you. A service
directory follows this escrow only, from the block where it is first started,
and reads the chain up to date before it answers
([chain-service.md](chain-service.md#running-the-server-on-a-chain)).

## Deploying (maintainers)

You need Foundry 1.8.6 ([contracts/README.md](../contracts/README.md)) and a
deployer key with some faucet ETH. The deployer gets no privilege.

1. **Keys.** Make the deployer, verifier and the three signer keys as
   encrypted keystores, for example
   `cast wallet new ~/secrets/orbit-watch deployer.json --password`.
2. **Settings.** Edit `contracts/deployments/base-sepolia.settings.json`:
   `safe_signers` (three addresses), `reviewers` (at least three),
   `verifier`, `fee_recipient` (`"safe"`, an account or the zero address for no
   platform fees), `token` (Circle's testnet USDC; the script refuses another
   token on Base Sepolia) and `safe_salt_nonce`.
3. **Simulate, then deploy and verify the sources on Sourcify** (no API key):

   ```sh
   cd contracts
   export ORBIT_WATCH_DEPLOY_SETTINGS=deployments/base-sepolia.settings.json
   export ORBIT_WATCH_DEPLOY_RECORD=deployments/base-sepolia.json
   RPC=https://sepolia.base.org
   KEY="--keystore $HOME/secrets/orbit-watch/deployer.json"
   forge script script/DeployOrbitWatch.s.sol --rpc-url $RPC $KEY            # simulation only
   forge script script/DeployOrbitWatch.s.sol --rpc-url $RPC $KEY --broadcast --slow \
     --verify --verifier sourcify
   ```

   The script writes the record while it runs; `--broadcast` then sends the
   transactions, `--slow` one at a time.
4. **Check** the deployed contracts against the record, then give the package
   the record:

   ```sh
   forge script script/DeployOrbitWatch.s.sol --sig "check(string)" \
     deployments/base-sepolia.json --rpc-url $RPC
   cp deployments/base-sepolia.json ../core/src/orbit_watch/chain/deployments/
   ```

   A test keeps the two copies equal and the record consistent with the
   settings. The same script runs in CI against a local Anvil chain that has
   Base Sepolia's EAS and Safe code
   ([`core/tests/test_deploy_script.py`](../core/tests/test_deploy_script.py)).

## Changing the reviewer list

Two signers sign a Safe transaction that calls the timelock's `schedule` with
the registry call (`addReviewer`, `removeReviewer` or `setAffiliation`) and a
delay of 48 hours. After 48 hours anyone calls the timelock's `execute` with
the same call. The tests show the whole sequence
([`OrbitWatchGovernance.t.sol`](../contracts/test/OrbitWatchGovernance.t.sol)).
The simulated reviewers with declared affiliations (`reviewer:sim-bertil`
and `reviewer:sim-dana`) are not in the first deployment; they can be added
this way, each with its affiliation.
