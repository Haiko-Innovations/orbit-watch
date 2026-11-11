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
  verification reports. CI regenerates it and requires a byte-identical result.
