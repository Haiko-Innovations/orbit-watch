# The phase 3 demo on Base Sepolia

> **Base Sepolia testnet, no real value.** The token is Circle's test USDC.
> Every station, observation, request and reviewer is SIMULATED.

The whole chain in the browser, every role in its own browser with its own
wallet, recorded on 2026-11-13 (step 3.8,
[D-33](../../docs/decisions.md#d-33-the-phase-3-demo-and-the-accessibility-review)):

- [`transcript.md`](transcript.md): every step, with screenshots, every
  transaction on BaseScan, every attestation on EAS Scan, and the timelock's
  operation;
- [`summary.json`](summary.json): the same, for programs;
- [`screenshots/`](screenshots): what each role saw;
- [`safe-batch-add-reviewer.json`](safe-batch-add-reviewer.json): the batch
  file that the administrator view prepared for the Safe app's Transaction
  Builder.

The run took under three minutes. `npm run demo:base-sepolia` in `web/`
made it ([web.md](../../docs/web.md#the-phase-3-demo)). Videos of every role's
browser stayed in the run's directory, outside the repository.

## The runs

- **SIM-REQ-3801 and SIM-REQ-3802** stopped in the browser, before the
  challenge, on mistakes of the demo itself:
  - the requester's page was not loaded afresh;
  - after a reload, the page asked which wallet to send with.

  Their requests were funded, reserved, delivered and verified on chain. After
  their challenge periods, each run's own service settled them as accepted
  (`admin tick`, [3801](https://sepolia.basescan.org/tx/0x565c07df9bc1c7bc7e951ae8120340f680e5ba58560a2c1c642e11671c62a346),
  [3802](https://sepolia.basescan.org/tx/0x8c34e3630cf72a799e5a8f8d084dad9c213567aec3b69aa5985a499f3b91ae67)).
- **SIM-REQ-3803** went through. Its Safe scheduled adding `reviewer:sim-bertil`
  in the timelock (operation
  `0xc78f6006382cafa3f750b1f67e1325b5340b0b2ee9042736265e04a2b90e3989`,
  [Safe transaction](https://sepolia.basescan.org/tx/0x4acbe1f646fba9682c7763d99b1aa164382620b0bb4f13ea72ee917dad98b395)),
  ready from 2026-11-15 18:37 UTC.
- **SIM-REQ-3804** is the run recorded here. One screenshot of the earlier run
  caught a section still loading, so the demo now waits for every section
  before a screenshot. Its Safe scheduled adding `reviewer:sim-dana`.

Phase 2 planned to add both reviewers this way
([D-24](../../docs/decisions.md#d-24-the-base-sepolia-deployment)). After 48
hours, anyone may execute the two operations, with the data or the execute
file from the administrator view.
