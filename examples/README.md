# Examples

> **Everything in this directory is SIMULATED or illustrative.** None of it is a
> real observation of a real object. Simulated files say so themselves:
> `"simulated": true` in JSON, `# orbit-watch: simulated=true` in IOD and
> `COMMENT orbit-watch simulated=true` in TDM.

- [`formats/`](formats): one small observation set in each supported format
  (JSON, IOD, CCSDS TDM) and a sites file. The `.iod` and `.tdm` files are
  generated from the JSON file with `orbit-watch convert`; a test keeps them in sync.
- [`simulated/`](simulated): the output of `orbit-watch demo`: a simulated
  request, reference orbits, allow-list and the six test deliveries with their
  verification reports, and in `quality/` three nights of a simulated station
  with the station quality meter's report. CI regenerates it and requires a
  byte-identical result.
- [`phase1/`](phase1): the output of `orbit-watch demo --phase 1`: five
  simulated requests through the whole request chain, with every outcome,
  the points and the reviewer profiles. CI regenerates it too.
- [`phase2/`](phase2): the output of `orbit-watch demo --phase 2`: the same
  five simulated requests on the Base Sepolia testnet (no real value), each
  party with its own wallet, with links to every transaction and attestation.
  It is a record of one run on a live chain, so CI does not regenerate it; CI
  runs the same demo on a local chain instead.
- [`real-iod/`](real-iod): how to run the quality meter on real IOD
  observations, and why no real example is committed yet.
