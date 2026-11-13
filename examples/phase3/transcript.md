# Phase 3 demo on Base Sepolia: transcript

> **Base Sepolia testnet, no real value.** The token is Circle's test USDC. Every
> station, observation, request and reviewer is SIMULATED. Written by
> `web/demo/base-sepolia.demo.ts` ([README](README.md)).

Request **SIM-REQ-3804**: every role in its own browser with its own wallet.

## Steps

1. **administrator (command line)**: Registers the reviewers' wallets, and its own, with the service. Reviewers: reviewer:sim-aino, reviewer:sim-chen, reviewer:sim-eero, reviewer:sim-fatima.
2. **visitor**: Opens the network page: Base Sepolia, the contracts, no sign-in.
   - [The network page on Base Sepolia, with the testnet label.](screenshots/01-network.jpg)
3. **requester:sim-cubesat-team**: Signs up with its own wallet (Sign-In with Ethereum).
   - [Signing up as a requester with the wallet.](screenshots/02-sign-up.jpg)
4. **requester:sim-cubesat-team**: Creates SIM-REQ-3804: SIM-CUBESAT-A, the window of 1-2 November 2026, minutes-long deadlines; publishes it and deposits its rewards.
   - [The new request's form.](screenshots/03-new-request.jpg)
   - [Before the wallet: what each transaction does, read from its call data.](screenshots/04-deposit-check.jpg)
   - [Funded: the deposit is in the escrow.](screenshots/05-funded.jpg)
5. **station:SIM-ESPOO**: Signs up, registers its SIMULATED station, reserves the request, simulates observations with its profile and delivers them.
   - [The station's SIMULATED profile.](screenshots/06-station.jpg)
   - [Delivered and verified, check by check.](screenshots/07-verified.jpg)
6. **requester:sim-cubesat-team**: Challenges the passed result; the escrow chooses three reviewers from the registry.
   - [Challenged: three reviewers chosen on chain.](screenshots/08-challenged.jpg)
7. **reviewer:sim-chen**: Approves with reasons: its vote is an EAS attestation it signs.
   - [The vote, checked before signing.](screenshots/09-vote-check.jpg)
8. **reviewer:sim-aino**: Approves with reasons: its vote is an EAS attestation it signs.
9. **service (verifier key)**: Two approvals of three decide the round; the service settles the request on chain.
   - [Settled: who gets what, and the chain's events.](screenshots/10-settled.jpg)
10. **station:SIM-ESPOO**: Withdraws its credit from the escrow with its own wallet.
   - [The reward withdrawn; the transactions listed.](screenshots/11-withdrawn.jpg)
11. **requester:sim-cubesat-team**: Withdraws its credit from the escrow with its own wallet.
12. **admin:orbit-watch-demo**: Signs in with its wallet: every request, payment, transaction and event; runs the simulator; prepares adding a reviewer for the Safe.
   - [The administrator view.](screenshots/12-admin.jpg)
   - [The Safe transaction, prepared for the Safe app.](screenshots/13-safe-proposal.jpg)
13. **Safe owners (2 of 3)**: Schedule the batch file's transaction in the timelock: 0xc3536c018f1050f23cb85d1511173840c5ce636ecaaf5d87c7ca83619076455f. Anyone may execute it after 48 hours.
   - [The timelock's operation, waiting out its 48 hours.](screenshots/14-timelock.jpg)
14. **visitor**: Browses the attestations, with EAS Scan links, without signing in.
   - [The attestation browser.](screenshots/15-attestations.jpg)
15. **visitor**: Measures a SIMULATED observation file's quality without signing in.
   - [The station quality meter.](screenshots/16-quality.jpg)

## Transactions

| Party | Action | Request | Status | Transaction |
|---|---|---|---|---|
| requester:sim-cubesat-team | approve | – | confirmed | [`0x3f5d9b0f638a75c2…`](https://sepolia.basescan.org/tx/0x3f5d9b0f638a75c21f538b7909dbc0e0662dc144aeee143dab1a992d040d91a3) |
| requester:sim-cubesat-team | fund | SIM-REQ-3804 | confirmed | [`0x6a7edfd53c9dd7ae…`](https://sepolia.basescan.org/tx/0x6a7edfd53c9dd7ae1e5d8735984517063775b95de282f702ce49d8e1ef8893b4) |
| station:SIM-ESPOO | reserve | SIM-REQ-3804 | confirmed | [`0x6f10cd45a705d68f…`](https://sepolia.basescan.org/tx/0x6f10cd45a705d68f19c64e32abd9825136977231221f1a8f95bb973f30899448) |
| station:SIM-ESPOO | deliver | SIM-REQ-3804 | confirmed | [`0x95d35e4aa6ff95f6…`](https://sepolia.basescan.org/tx/0x95d35e4aa6ff95f6529f1cd9e1be8971e110018385dcd40893bd71b71e8348ad) |
| system:verifier | attest_result | SIM-REQ-3804 | confirmed | [`0xaea4b43d97cb4bb4…`](https://sepolia.basescan.org/tx/0xaea4b43d97cb4bb4cb34f9e0dcfe802e0bfc93e26954b5e3ce506467c51c9011) |
| requester:sim-cubesat-team | challenge | SIM-REQ-3804 | confirmed | [`0xa857fdedf93b0566…`](https://sepolia.basescan.org/tx/0xa857fdedf93b056652bdf8c623692abeed632e378c0fd1c98be071b68f305cdf) |
| reviewer:sim-chen | attest_vote | SIM-REQ-3804 | confirmed | [`0x9cc45ff058b1430e…`](https://sepolia.basescan.org/tx/0x9cc45ff058b1430e4e58a05e0c3ffe76b5a966c16ee027bd4b11e48062e62645) |
| reviewer:sim-aino | attest_vote | SIM-REQ-3804 | confirmed | [`0x3bfbba86521ef296…`](https://sepolia.basescan.org/tx/0x3bfbba86521ef2961a0e4a21ab89420f5b076e0907335afbd10d2134d5347be1) |
| system:verifier | settle | SIM-REQ-3804 | confirmed | [`0xd1f0bb6d331ad6ed…`](https://sepolia.basescan.org/tx/0xd1f0bb6d331ad6eda46d365317343d8b029c38a76f4725ec489e2072e39ba1ba) |
| station:SIM-ESPOO | withdraw | – | confirmed | [`0x364808b1e99f9b48…`](https://sepolia.basescan.org/tx/0x364808b1e99f9b485d563f91d7ffd1be7e3cb4a358120484d5bae2b5237679d8) |
| requester:sim-cubesat-team | withdraw | – | confirmed | [`0x9a6bc60aa3cd7468…`](https://sepolia.basescan.org/tx/0x9a6bc60aa3cd7468e6c226ca43e1d2f6cf79a332b08b505fed6aec18ada0d55e) |

## Attestations

| Request | Kind | By | Attestation |
|---|---|---|---|
| SIM-REQ-3804 | vote | 0xdd53Ebe04af0BEbcE35365170478ae8291079c65 | [`0xa3e7412aec1c9c5c…`](https://base-sepolia.easscan.org/attestation/view/0xa3e7412aec1c9c5c4e0951945fdc0eb9ca23cc864cde972cb415f905e6f3e4ea) |
| SIM-REQ-3804 | vote | 0x600e4f215b7209b9Dc7BB0F507a8A4DCe894D219 | [`0x7b107ad5f718b3f0…`](https://base-sepolia.easscan.org/attestation/view/0x7b107ad5f718b3f081f0481bdeb5c9b09da407e6d322b6e6e0d8fabfbb1a47b7) |
| SIM-REQ-3804 | result | service (verifier key) | [`0x5637a9f6b44dbcc6…`](https://base-sepolia.easscan.org/attestation/view/0x5637a9f6b44dbcc62aa724c99578ff9e23f481d2a751accaaf740fb7b63b9a1a) |

## The timelock

- `0x7888f2b8b3bef5373e933ffec2311979cf96567484195535df0cf1bba7d774ba`: registry.addReviewer(0x7fab546139bAea864995bABB60696b5a9DC24b91), waiting, ready from 2026-11-15T18:41:33.000Z; scheduled by the Safe in [`0xc3536c018f1050f2…`](https://sepolia.basescan.org/tx/0xc3536c018f1050f23cb85d1511173840c5ce636ecaaf5d87c7ca83619076455f).

The Safe's batch file the administrator view prepared: [safe-batch-add-reviewer.json](safe-batch-add-reviewer.json).
