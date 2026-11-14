# Decentralisation: the long-term direction

Written on 2026-11-14, from a discussion with the maintainer. This is a
direction, not a plan. Every step below needs its own proposal and decision
([decisions.md](decisions.md)) before any work starts. Phase 4 only promises
not to close this way
([P4-15](decisions.md#p4-15-nothing-that-closes-the-way-to-a-community-network)).

## The goal

Orbit Watch should depend on no single person, machine or company, and the
community should decide how its network is run. A good community and a
network of nodes the community runs are the way there. One rule from the
starting plan stays: **no token of our own** for investment or governance
([plan.md](plan.md#2-key-constraints)).

## What Bitcoin shows

Bitcoin is the best-known network with no owner. Six of its habits matter
here:

1. **Every node checks everything itself.** A full node trusts no one; it
   verifies every block and transaction against the rules.
2. **Development is open, and upgrading is voluntary.** Bitcoin Core is
   developed in public. Its maintainers merge changes, but nobody can make a
   node upgrade: each operator chooses the version it runs. There are no
   automatic updates, on purpose, because they would give the developers power
   over the network.
3. **Rule changes need broad agreement.** They go through a public proposal
   process (BIPs) and take effect only when enough of the network is ready, as
   SegWit did in 2017 and Taproot in 2021.
4. **Leaving is the last check.** When the community could not agree, part of
   it left and started its own chain (Bitcoin Cash, 2017). The right to fork
   keeps governance honest.
5. **Reproducible builds.** Several independent people build each release
   from the source and sign the results' hashes, so nobody has to trust
   whoever published it.
6. **No admin keys.** No key can steer the network; funds are on their
   owners' keys.

What differs for Orbit Watch:
- **It is an application on another chain.** It can be no more decentralised
  than the chain under it. Base Sepolia is right for the testnet, but Base's
  sequencer is run by one company; before any mainnet, the choice of chain
  must be made again with this in mind.
- **Calibration needs a secret.** A calibration task works only if the
  reviewer does not know the answer, so someone has to know it. Bitcoin has
  nothing like it.

## Where Orbit Watch stands

| Layer | Now | Decentralised | How hard |
|---|---|---|---|
| Money and outcomes | the escrow contract on chain | the same | done |
| Results and votes | EAS attestations | the same | done |
| Observing stations | the community's own equipment | the same | done |
| Web application | served by the service | static files that anyone can serve | easy |
| API and reads | one service | stateless nodes that read the truth from the chain | moderate |
| Files | one database | copies on several nodes, found by their SHA-256 | moderate |
| Automated verification | **one verifier key** | several registered verifier nodes, agreeing k of n | hard |
| Calibration tasks | the service knows the answers | no good design yet | hardest |
| Updates | releases | signed, reproducible releases; approved method versions on chain | moderate |
| Governance | the maintainer holds the Safe's keys (D-24) | signers chosen by the community | social, not technical |

## Two tracks

### Governance

1. **A public proposal process**, like Bitcoin's BIPs. A change is written
   down, discussed in the open and ends in rough consensus.
2. **Signers from the community.** The Safe's signers are people from the
   community, in different countries and organisations, for example 3 of 5,
   then 5 of 9. They carry out decisions, and the community can replace them
   (`swapOwner`). The timelock gives everyone time to react to a change.
3. **No single person in any account.** Several maintainers can merge and
   administer the GitHub organisation; domains and service accounts have
   several holders; several people sign releases.
4. **A neutral home.** Haiko Innovations Oy owns the repository and the name
   today. An association or a foundation would make the project independent
   of a company too. There is no hurry.
5. **The right to leave.** The code is Apache 2.0 and the data CC BY 4.0, so
   anyone can continue with an escrow of their own.

Decisions without a token are hard on purpose. Token votes let money decide;
rough consensus, elected signers, delays and the right to leave do not.

### The node network

1. **Static web application, stateless API nodes.** Anyone can serve the web
   application. API nodes keep no state of their own: they read the truth from
   the chain and the files. Phase 4 builds exactly such a service (P4-05,
   P4-06).
2. **Files on many nodes.** Files are already named by their SHA-256, which
   is on chain, so any node can serve a file and anyone can check it.
3. **Verifier nodes instead of one key.** Verification is deterministic and
   versioned ([D-03](decisions.md#d-03-deterministic-versioned-verification)):
   the same inputs give a byte-identical report. Several registered verifier
   nodes can each attest, and a new escrow version accepts a result when k of
   n agree. No shared key is needed. This is the largest change: a new escrow,
   a verifier registry, and incentives against collusion (the bonds that are
   already an open question).
4. **Rules activate on chain; software is never pushed.** Nodes upgrade when
   their operators choose. A new verification method version is approved on
   chain by the community's decision, behind the timelock's delay, and results
   from older versions stop counting when it activates. Releases are
   reproducible and signed by several people, so a bad release cannot slip
   into every node at once.

## Help wanted

There is no community yet to share the keys and the work with, so the
maintainer still holds the Safe's keys (P4-11). We are looking for people who
would sign for the Safe, co-maintain the project or sign releases:
[#77](https://github.com/Haiko-Innovations/orbit-watch/issues/77).

## Open problems

- **Calibration without a trusted party**: for example commit and reveal
  among several calibration providers. This is research, not engineering.
- **Incentives without a token**: node operators paid from request fees
  (USDC), or volunteers, as amateur ground station networks run today.
- **Sybil resistance**: who may run a verifier node? A registry under
  governance, bonds, or both.
- **Personal data**: nothing can be deleted from data spread over many nodes,
  and every node operator becomes a controller or processor. Station
  coordinates need a strict rule.
- **Scale**: one central service and a few mirrors may serve a small
  community for a long time. Decentralisation costs complexity and latency,
  and should come when the community needs it.

## A possible order

1. **Phase 4**: the public sandbox, stateless and portable. The Safe's keys
   stay with the maintainer until there are people to share them with (P4-11,
   [#77](https://github.com/Haiko-Innovations/orbit-watch/issues/77)).
2. **Governance**: the proposal process, several maintainers and account
   holders, signed reproducible releases, community signers.
3. **Nodes**: static web application and stateless API nodes run by others,
   files mirrored between them.
4. **Verifier network**: escrow version 2, verifier nodes agreeing k of n,
   method versions activated on chain.

Each step is useful on its own, and none forces the next.
