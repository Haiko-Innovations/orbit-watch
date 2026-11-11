# Station quality meter

`orbit-watch score-station` tells an observer how good their own observations
are, using nothing but public orbit data. It is the part of Orbit Watch that
is useful to an observer from day one, before any requests exist.

```sh
orbit-watch fetch-gp --group cubesat -o cubesat.json      # public reference orbits
orbit-watch score-station my-night.iod --sites my-site.json --catalog cubesat.json
```

Input: one or more observation files (Orbit Watch JSON, IOD or CCSDS TDM) from
one station, a sites file with the station coordinates (for IOD and TDM), and
GP data that covers the observed objects with an epoch within 7 days of the
observations.

## What it reports

| Number | How it is computed | What it tells you |
|---|---|---|
| **Angle precision** | Cross-track residuals, minus a straight-line trend per pass, RMS | How precisely you measure positions. Errors of the reference orbit are smooth over a pass and mostly drop out. |
| **Timing precision** | Along-track residuals in seconds, minus a trend per pass, RMS | How consistent your timestamps are (it also holds the along-track part of the angle noise). |
| **Timing offset** | Mean along-track residual in seconds | Positive: objects appear ahead of their predictions; negative: behind. |
| **Per night** | The same numbers per observing night (local solar date) | How your station develops over time, for example after a change of equipment or time synchronisation. |

The meter compares the precision numbers with the uncertainties you declare
and says whether your declared uncertainties look realistic.

## Clock errors versus orbit errors

A station clock that runs ahead of UTC makes **every** object appear behind
its prediction by the same number of seconds. An error in one object's
reference orbit makes only **that** object appear ahead or behind. The meter
therefore reports a clock error only when at least two objects share the same
offset on a night; with one object it says that the two cannot be told apart.

Public GP orbits are good to about a kilometre at epoch and get worse with
age. Absolute residuals are therefore not a measure of station quality on
their own; the meter says so in every report.

## Example (SIMULATED)

[`examples/simulated/quality/`](../examples/simulated/quality) holds three
nights of a simulated station whose clock starts running 0.25 s ahead of UTC
on the third night. The report finds the clock error and the change:

```text
  - 3 objects appear on average 0.25 s behind their predictions on the latest night. A shared offset points to your clock: your timestamps seem to run about 0.25 s ahead of UTC. ...
  - The mean timing offset changed from +0.00 s (night of 2026-11-02) to -0.25 s (night of 2026-11-03).
```

For real data, see [`examples/real-iod/`](../examples/real-iod).
