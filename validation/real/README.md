# The validation set: more real observations from SCORE

> **Real data.** These are real observations of real satellites, made and published by
> the observers named in [CREDITS.md](CREDITS.md). Nothing here is SIMULATED.

Step 5.3 measures the verification method on real data (decision
[P5-07](../../docs/decisions.md#p5-07-measure-first)). Its results are in
[docs/real-data-validation.md](../../docs/real-data-validation.md). This set adds 38
tracks to the 18 of [`examples/real/`](../../examples/real), from the same instruments
and observers: 13,713 observations from 5 stations. The measurement runs over both
sets.

| Instrument | Tracks | Objects |
|---|---|---|
| Video camera (WATEC 902H2, 85 mm lens), Leiden | 4 | ACS 3, four more nights |
| DECam on the 4 m Blanco telescope, Cerro Tololo | 7 | Rocket bodies, debris and old geostationary satellites |
| Phone (iPhone 12 Mini), September and November | 21 | Starlink satellites, SAOCOM 1-A, POISK, rocket bodies |
| Phone (iPhone 17 Pro) | 6 | SAOCOM 1-A, GALILEO 20, rocket bodies |

The observers published them in [SCORE](https://score.cps.iau.org), the IAU CPS's
Satellite Constellation Observation Repository, under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Only civilian objects
([D-05](../../docs/decisions.md#d-05-civilian-objects-only-through-an-allow-list)):
[`tracks.json`](tracks.json) lists the windows fetched, and the six it did not fetch
with the reason for each.

## What the files hold

- [`observations/`](observations): observation sets in format 1.1, as in
  `examples/real/` ([its README](../../examples/real/README.md#what-the-files-hold)
  says what they hold). **60″ is assumed** for every angle uncertainty SCORE does not
  give, and each file says so. One night of ACS 3, 2024-09-21, has the uncertainties
  its observer gave.
- **Observations left out.** A phone's place sometimes jumps for one observation,
  by 0.1 to 10 km, and comes back for the next. The converter leaves such an
  observation out when the others of the track share one place, and the file says how
  many and how far (decision
  [D-46](../../docs/decisions.md#d-46-the-method-measured-on-real-data)). Four tracks
  of 2026-09-30 lose 21 observations this way.
- [`reference-orbits.json`](reference-orbits.json): the element sets, from the IAU
  CPS's SatChecker. They are not committed
  ([D-06](../../docs/decisions.md#d-06-no-real-orbit-data-in-the-repository)). For each
  track, the set nearest its middle; and for each track that passes, the sets nearest
  1, 3, 7 and 14 days before its middle, for the age study.
- [`results.json`](results.json): everything the measurement found, track by track,
  and the SHA-256 of every input.
- [`known-answers.json`](known-answers.json): the tracks whose correct answer is
  settled, for reviewer calibration
  ([reviewer-accuracy.md](../../docs/reviewer-accuracy.md#real-known-answer-tasks)).

## Measuring

From the repository's `core` directory, fetch the element sets into the cache, then
measure:

```sh
orbit-watch fetch-orbits ../examples/real/reference-orbits.json
orbit-watch fetch-orbits ../validation/real/reference-orbits.json
orbit-watch measure-method
```

`measure-method` writes `results.json`, `known-answers.json` and the tables of
`docs/real-data-validation.md`. With `--check` it writes nothing and fails if any of
them is not what the measurement gives, which a test checks in CI. It takes about a
minute.

## Made with

For each window in `tracks.json`, a second or more apart and stopping at the first
problem:

```sh
orbit-watch fetch-score --catnr 59588 --start 2024-09-09T12:00:00Z --end 2024-09-10T12:00:00Z -o raw/59588-2024-09-09.json
```

then, with the raw files of `examples/real` first, so that the stations are the same:

```sh
orbit-watch convert-score raw-examples/*.json raw/*.json --out converted \
  --assume-angle-uncertainty 60
```

The files of `examples/real/` come out unchanged, and the others are this set. The
element sets were named with `fetch-satchecker --manifest
../validation/real/reference-orbits.json`, two seconds apart: `--near` the middle of
each track, and 1, 3, 7 and 14 days before it for the tracks that pass. Fetched on
2026-11-21.

## Personal data and credits

As in [`examples/real/`](../../examples/real/README.md#personal-data): a station's place
may be someone's home, and an ORCID iD names a person. The observers published both
in SCORE themselves, and the
[privacy notice](../../docs/legal/privacy-notice.md#observations-that-others-have-published)
covers this set too. An observer can ask for their observations to be removed: write
to info@haikoinnovations.com with "Orbit Watch privacy" in the subject line.

[CREDITS.md](CREDITS.md) names the observers of each file, with the statements that
SCORE and SatChecker ask users to show. A test checks that it is what the converter
writes for these files.
