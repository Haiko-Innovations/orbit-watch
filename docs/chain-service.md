# The service on a testnet chain

Phase 2, step 2.6. Code: [`chain/link.py`](../core/src/orbit_watch/chain/link.py)
(the service's side), [`chain/wallet.py`](../core/src/orbit_watch/chain/wallet.py)
(the user's side), the [HTTP API](api.md#on-a-testnet-chain) and the
[command line](api.md#command-line-client). Decisions
[P2-09](decisions.md#p2-09-keys-and-wallets),
[P2-10](decisions.md#p2-10-the-chain-decides-payment-status) and
[D-23](decisions.md#d-23-the-service-on-a-chain).

> **Testnet only, no real value.** The service runs only on Base Sepolia
> (84532) or a local Anvil chain (31337), and every chain-related answer says
> so ("Base Sepolia testnet, no real value"). It still runs locally: phase 2
> has no public deployment ([P2-11](decisions.md#p2-11-phase-2-has-no-public-deployment)).

With a chain, every **funded** request lives on the
[escrow contract](escrow.md) and its [attestations](attestations.md).
Unfunded requests never touch the chain and work as in phase 1.

## Who signs what

Every party has its own wallet and signs its own transactions. The service
never sees a party's key. It holds one key of its own, the verifier key.

| Step | Signed by | On chain | What only the service gets |
|---|---|---|---|
| fund | the requester | `approve` of exactly the deposit, then `escrow.fund` | |
| cancel (before a reservation) | the requester | `escrow.cancel`, which refunds at once | |
| reserve | the station | `escrow.reserve` | |
| deliver | the station | `escrow.deliver` with the file's SHA-256 | the observation file |
| automated result | the service (verifier key) | EAS attestation, result schema | the report |
| challenge | the requester or the observer | `escrow.challenge` with the reason's SHA-256 | the reason's text |
| vote | the reviewer | EAS attestation, vote schema | the reason's text |
| settle | the service (anyone may) | `escrow.settle` | |
| withdraw | each party | `escrow.withdraw`: a token transfer | |

For each step a party asks the API as in phase 1. For a funded request, the
API answers `202 Accepted` with the **unsigned transactions** to sign:
`chainId`, `from`, `to`, `data` and `value`, without nonce, gas or fees. The
party's wallet fills those in, signs and sends. The party then reports each
transaction's hash (`POST /v1/transactions`). Until the chain confirms a
transaction, nothing changes.

The station uploads its observation file with the step that prepares `deliver`,
or afterwards if it delivered on chain first. The service runs automated
verification as soon as it holds the file of a delivery that is on chain.

## The chain decides

The service follows the escrow's events, from its deployment block onwards, at
the start of every API call. It applies each event to the request's lifecycle
record at its block's time, one transaction at a time, by the same rules as in
phase 1:

- **Reviewer rounds come from the chain.** The escrow chooses the three
  reviewers from the on-chain registry, and the service assigns them their
  tasks.
- **Payments come from the chain.** When a request is settled, the service
  compares the escrow's payouts with the settlement rules
  (`settlement_plan`), payout by payout. The settlement it shows names the
  settling transaction.
- **Deadlines are the chain's.** The service's clock is the latest block's
  time, the same clock the escrow's deadlines use.

**A request is on chain from its funding.** The `Funded` event must come from
the requester's registered wallet, with the request's terms (the SHA-256 of
the frozen terms and every time limit). Anything else, for example someone
funding the same request ID first, is a **conflict**: it is shown with the
request and never applied. The requester then creates the request again under
a new ID. Events of a request that is not on chain are ignored.

**The service's own part.** When a party reports a transaction, and when an
admin calls `tick`, the service attests the automated result of each delivery
it holds a file for, and settles each request whose outcome is reached. The
verifier key signs both. A refusal is shown as a conflict.

**Transactions** that parties report and that the service sends are shown
apart as `pending`, `confirmed` or `failed`, each with a block explorer link
(`https://sepolia.basescan.org/tx/…`; a local chain has none). A failed
transaction shows the contract's reason when the node can replay it, for
example `not_a_reviewer`.

## Wallets

A party registers one wallet address by signing the API's registration
message (EIP-191, as `cast wallet sign` does):

```text
Orbit Watch wallet for requester:alice on chain 84532, escrow 0x…
```

The message names the party, the chain and the escrow, so the signature
cannot register the address for anyone or anywhere else. Each party has one
wallet and each address belongs to one party. A wallet cannot be changed in
phase 2.

**Reviewers register before they can be chosen.** A reviewer in a round
whose address no party has registered appears as `wallet:<address>`. Such a
reviewer gets no tasks, but can still vote straight on chain.

## Running the server on a chain

```sh
orbit-watch serve --dir ./ow-testnet --network base-sepolia \
  --verifier-keystore ~/secrets/orbit-watch/verifier.json
```

`--network base-sepolia` takes the escrow, its first block and Base's public
RPC endpoint from the deployment record in the package
([base-sepolia.md](base-sepolia.md)); `--chain-rpc` overrides the endpoint.
For another escrow, for example on a local chain, give `--chain-rpc`,
`--escrow` and `--from-block` instead.

- The verifier keystore is an encrypted JSON keystore, for example one made
  with `cast wallet import`. Keep it outside the repository and readable only
  by you; the server warns otherwise. Its password comes from
  `--verifier-password-file`, from `$ORBIT_WATCH_VERIFIER_PASSWORD_FILE` or
  from a prompt. The key must be the escrow's verifier, and it needs testnet
  ETH for gas.
- A service directory follows one escrow on one chain, from its first start.
  Another chain or escrow is refused, and so is a directory that was started
  without a chain.
- Points are not used on chain: `admin grant` is refused, and `balance` shows
  the wallet's tokens and what it can withdraw.

The deployment script and the Base Sepolia deployment are described in
[base-sepolia.md](base-sepolia.md) (step 2.7). The tests set up their local
chains themselves ([`core/tests/chain_world.py`](../core/tests/chain_world.py)).

## The command line

Every API command takes the signing options:

| Option | Default | |
|---|---|---|
| `--keystore FILE` | `$ORBIT_WATCH_KEYSTORE` | your encrypted keystore, e.g. `~/.foundry/keystores/<name>` |
| `--password-file FILE` | `$ORBIT_WATCH_PASSWORD_FILE` | otherwise the password is asked for |
| `--rpc URL` | `$ORBIT_WATCH_RPC`, or on Base Sepolia its public endpoint | the endpoint your wallet sends through |
| `--unsigned` | | print the transactions for another wallet instead |

The key is decrypted in the command's own process and is never sent anywhere.
Orbit Watch never asks for a seed phrase or a private key, and never takes a
password on the command line.

```sh
cast wallet import alice                     # once: your own encrypted keystore
export ORBIT_WATCH_KEYSTORE=~/.foundry/keystores/alice   # --rpc: Base Sepolia's public endpoint
orbit-watch chain                            # the network, the escrow, the token, the notice
orbit-watch wallet register                  # signs the registration message
orbit-watch request fund SIM-REQ-0001 --observer 1.5 --reviewer 0.1   # token amounts
orbit-watch request show SIM-REQ-0001        # the record, its events and explorer links
orbit-watch balance requester:alice          # tokens in the wallet and to withdraw
orbit-watch wallet withdraw                  # transfer what was credited to you
orbit-watch tx list                          # pending, confirmed and failed
```

Amounts on a chain are token amounts (`1.5` is 1.5 USDC); the command line
converts them with the token's decimals, read from the token contract.

**With another wallet:** `--unsigned` prints the transactions and the order
to send them in. Send each one, for example with `cast send <to> --data
<data> --rpc-url … --account <name>`, then report its hash with
`orbit-watch tx report <hash>`. To register such a wallet, print the message
with `orbit-watch wallet register --print-message`, sign it (`cast wallet sign
"<message>" --account <name>`) and pass `--address` and `--signature`.

## Limits in phase 2

- **Calibration tasks can be told apart from real ones** on chain. A real
  vote is the reviewer's own public attestation, so the API asks for a
  signature; a calibration answer stays off chain. Calibration still measures
  accuracy, but no longer unseen (D-23).
- **Someone can fund a request's ID first.** The request IDs of open requests
  are visible to the API's users. The service shows this as a conflict, and
  the requester creates the request again under a new ID.
- **No background worker.** The service follows the chain on every API call
  and does its own part when a transaction is reported and on `tick`.
- **Reorganisations are not handled.** The service applies every block it
  reads. Base Sepolia rarely reorganises, and this is a testnet.

## Tests

On a local Anvil chain, in the `tarkistus` check:

- [`core/tests/test_chain_service.py`](../core/tests/test_chain_service.py):
  accepted, challenged and rejected, inconclusive and disputed, cancelled and
  expired requests through the API. Also:
  - unauthorised parties cannot vote or withdraw, through the API or straight
    on chain, and a failed transaction shows as failed;
  - a retry never pays twice;
  - someone else funding a request ID is a conflict;
  - the service catches up with the chain after a restart;
  - the server starts only with the escrow's verifier key.
- [`core/tests/test_cli_chain.py`](../core/tests/test_cli_chain.py): the
  whole chain from the command line against a real HTTP server, with every
  party's own encrypted keystore, and one step signed by "another wallet". It
  records every byte that reaches the server and checks that **no private
  key, keystore or password is ever among them**, nor in anything the service
  stores.
