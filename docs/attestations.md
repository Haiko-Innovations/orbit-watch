# Attestations and reviewer rounds

Phase 2, step 2.3. Code: [`contracts/src/OrbitWatchEscrow.sol`](../contracts/src/OrbitWatchEscrow.sol)
and [`contracts/src/OrbitWatchReviewerRegistry.sol`](../contracts/src/OrbitWatchReviewerRegistry.sol).
Decisions [P2-03](decisions.md#p2-03-eas-attestations-with-two-schemas) and
[D-20](decisions.md#d-20-attestations-and-reviewer-rounds-on-chain).

> **Testnet only.** Everything here runs on Base Sepolia or a local chain.

The automated verification result and every reviewer's vote are public
[EAS](https://github.com/ethereum-attestation-service/eas-contracts)
attestations. Anyone can read and reuse them without Orbit Watch code. The
escrow contract is the **resolver** of both schemas: EAS calls it with each new
attestation, and an attestation the rules refuse is never created. The public
record therefore holds only attestations that counted.

## The two schemas

The escrow registers both schemas itself when it is deployed, as not
revocable: a result or a vote, once made, stands. Their UIDs are
`resultSchemaUid()` and `voteSchemaUid()`.

### Automated result

```
string requestId,bytes32 deliverySha256,bytes32 reportSha256,string verdict,string method,string methodVersion
```

| Field | Value |
|---|---|
| attester | the Orbit Watch verifier key (`verifier()`), and nobody else |
| recipient | the observer (the station that delivered) |
| `requestId` | the Orbit Watch request ID, for example `SIM-REQ-0001` |
| `deliverySha256` | the SHA-256 of the delivered file, as recorded by `deliver` |
| `reportSha256` | the SHA-256 of the verification report |
| `verdict` | `pass`, `fail` or `inconclusive` |
| `method`, `methodVersion` | the verification method, for example `orbit-watch-automated-verification`, `1.0.0` |

`pass` or `fail` starts the challenge period. `inconclusive` starts a reviewer
round at once.

### Review vote

```
string requestId,bytes32 deliverySha256,bool approve,bytes32 reasonSha256
```

| Field | Value |
|---|---|
| attester | the reviewer's own address |
| recipient | the observer |
| `refUID` | the UID of the automated result's attestation (`getRequest(id).resultAttestation`) |
| `approve` | true to accept the delivery, false to reject it |
| `reasonSha256` | the SHA-256 of the written reason (a reason is required) |

### What the escrow refuses

An attestation is refused, and so never created, when:

- it is not about a known request in the right status: a result needs a
  delivered request within its verification timeout, and a vote needs a
  reviewer round that is still open;
- its `deliverySha256` or recipient does not match the delivery;
- a result is not by the verifier, has an unknown verdict or no report hash;
- a vote is by anyone but one of the round's three reviewers, by a reviewer
  who is no longer registered, is a second vote, has no reason, or does not
  reference the result;
- it expires, is revocable, carries a payment, or uses another schema that
  names the escrow as its resolver;
- it comes in a batch of two or more (attest one at a time).

## Challenges

During the challenge period the requester or the observer calls
`challenge(requestId, reasonSha256)`. A challenge is a transaction, not an
attestation. It starts a reviewer round at once.

## Who reviews

Reviewers are listed in the reviewer registry, each with optional
**affiliations**: parties whose requests and deliveries they must never review
([D-13](decisions.md#d-13-optimistic-verification-rules)). Step 2.4 puts the
registry behind a Safe multisig and a 48-hour public timelock.

When a round starts, the eligible reviewers are the registered ones who are
neither the requester nor the observer and are affiliated with neither. The
three with the lowest score

```
keccak256(abi.encode("orbit-watch-reviewers/evm/1", requestId, deliverySha256, reviewer))
```

are chosen (`requestId` is the on-chain key, `keccak256` of the request ID).
Nobody picks them, not even the challenger, and anyone can recompute the
choice. This is the phase 1 rule
([optimistic-verification.md](optimistic-verification.md#who-reviews)) with
addresses in place of IDs and Keccak-256 in place of SHA-256. With fewer than
three eligible reviewers a challenge is refused and the request stays in its
challenge period. An inconclusive result is refused too, so the request
expires at its verification timeout and the requester gets everything back.

A reviewer removed from the registry can no longer vote, also in a round
already under way. If that leaves no majority, the round ends as a dispute.

## Testing against the real EAS

The tests do not use a mock. They place the runtime bytecode of the EAS and
SchemaRegistry contracts behind Base Sepolia's predeploys at the same
addresses (`0x4200…0021` and `0x4200…0020`), from
[`contracts/test/fixtures/base-sepolia-eas/`](../contracts/test/fixtures/base-sepolia-eas/README.md),
and refuse to run if its hash differs from the code on Base Sepolia. CI needs
no network access. The interfaces come from
[eas-contracts](https://github.com/ethereum-attestation-service/eas-contracts)
v1.4.0 (MIT), a submodule pinned by commit.

## Known limits

- The observer chooses the delivered file, and so its SHA-256, which is part of
  the reviewer score. By trying many variants of a file, an observer could
  steer which reviewers a later round gets. Phase 1 has the same property. A
  fix (for example, mixing in randomness the observer cannot know) is an open
  question.
- The verifier key is fixed when the escrow is deployed. A new key means a new
  escrow; requests in the old one settle there.
