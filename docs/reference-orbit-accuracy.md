# Reference orbits measured against operators' orbits

How far are CelesTrak's GP element sets from where the satellites really are, and how
does that grow with a set's age? Step 6.1 of phase 6 measures it before method 3.0.0
changes the limit's orbit term
([P6-02](decisions.md#p6-02-measure-first-again),
[D-60](decisions.md#d-60-reference-orbits-measured-against-operators-orbits)).

Today every reference orbit is assumed to be 5 km off
([D-08](decisions.md#d-08-the-residual-check-catches-gross-errors-not-arcsecond-accuracy)),
and sets up to 7 days old are accepted. Step 5.3 found both too loose for low orbits:
the 5 km was 97 % of a good video camera's limit, and a clock half a second wrong
passed in 33 of 35 low-orbit tracks
([D-46](decisions.md#d-46-the-method-measured-on-real-data)).

> **Real data, nothing committed.** The orbits are real, from CelesTrak and the IAU CPS's
> SatChecker. No element set is in the repository: the results name each set by its
> epoch and SHA-256 only
> ([P5-05](decisions.md#p5-05-orbit-data-stays-out-of-the-repository)).

## In short

- **A fresh GP set is far better than the 5 km assumed.** The newest set a service would
  have had, a median 0.2 to 0.6 days old, was a median 0.17 to 0.54 km off for Kuiper,
  OneWeb, the ISS, Planet and the laser-ranging satellites in low orbits. Its 90th
  percentile was below 1.4 km. AST SpaceMobile's was worse: 1.83 km, and 12.1 km at
  most.
- **In low orbits the error grows fast with the set's age, and along the track.** Over
  all low-orbit objects, the median was 0.33 km for sets under half a day old, 1.4 km
  at one to two days, 3.2 km at two to three, 10.7 km at three to five and 29 km at
  seven to ten. The 90th percentile was 1.9, 9.4, 21, 58 and 212 km. Nearly all of it is
  in track; the median cross-track and radial parts stay at 0.4 km or less.
- **How fast depends on the object.** The passive laser-ranging satellites stay near
  their fresh error: from 0.26 km to 1.0 km, the median, over ten days. The ISS, which
  fights drag and is reboosted, reaches 3 km at one to two days. Satellites that
  manoeuvre reach tens of kilometres within three to five days, and hundreds at the
  90th percentile: Kuiper's, Planet's, which keep their places by drag, and AST
  SpaceMobile's.
- **Medium orbits change slowly**: a median of 0.9 to 2.0 km over ten days. Six
  navigation satellites in geosynchronous orbits, of QZSS and NavIC, were 3 to 15 km
  off, the median, and up to 280 km, most likely after a manoeuvre.
- **The truth has its own error.** CelesTrak fitted the SupGP sets to the operators'
  data to a median of 0.11 to 0.33 km, so smaller differences cannot be told apart from
  SupGP's own.

This agrees with step 5.3: in low orbits sets about three days old already rejected
good tracks ([D-46](decisions.md#d-46-the-method-measured-on-real-data)).

## How it was measured

- **The truth** is CelesTrak's supplemental GP (SupGP): element sets that CelesTrak fits
  to operators' own orbits ([data-sources.md](data-sources.md#operators-orbits-celestraks-supplemental-gp)).
  - One download per source: AST SpaceMobile (`AST-E`), the laser-ranging predictions
    (`CPF`), the ISS (`ISS-E`), Kuiper (`Kuiper-E`), OneWeb (`OneWeb-E`) and Planet
    (`Planet-E`).
  - From each source and orbit class, up to six objects are taken, evenly by catalogue
    number. Each object's truth is its operator-derived set with the latest epoch at or
    before the run. For several sets at that epoch, such as several laser-ranging
    prediction centres, the one CelesTrak fitted best is used.
  - The ISS gives its last eight 6-hour segments that had begun. NASA's ephemeris
    behind them had been posted on 2026-11-23, so this run had two.
  - Starlink is left out: its list is large, and CelesTrak limits it.
- **The GP sets** are every OMM that SatChecker keeps of the object from ten days before
  the truth's epoch up to it: one request per object, two seconds apart. CelesTrak's
  and Space-Track's copies of one set count once.
- **The comparison.** "SupGP data is fitted from the current epoch forward", so both
  sets are propagated with SGP4 every minute over the six hours after the truth's epoch.
  - The difference is split into radial, in-track and cross-track parts in the truth's
    frame. Each comparison gives the RMS of each part and of the whole.
  - A set's age is taken at the middle of the six hours.
- **The truth's own error.** CelesTrak gives the RMS of each SupGP fit to the operator's
  data. That RMS bounds how much of a difference is SupGP's own.

<!-- measured:run -->
Run fetched 2026-11-23T21:05:00Z: 44 truth sets of 43 objects, 2158 comparisons with GP sets, 0 not propagated, 2 left out as the truth itself.
<!-- /measured:run -->

### The sources

<!-- measured:sources -->
| Source | Objects | Truth sets | SupGP's own fit, median (km) | GP sets compared |
|---|---|---|---|---|
| `AST-E` | 6 | 6 | 0.25 | 292 |
| `CPF` | 18 | 18 | 0.32 | 672 |
| `ISS-E` | 1 | 2 | 0.11 | 94 |
| `Kuiper-E` | 6 | 6 | 0.24 | 324 |
| `OneWeb-E` | 6 | 6 | 0.26 | 346 |
| `Planet-E` | 6 | 6 | 0.33 | 430 |
<!-- /measured:sources -->

## The set a service would use

For each truth, the newest GP set at or before its epoch: the set that the service's
follower would have had (step 5.4).

<!-- measured:newest_set -->
| Source | Orbit | Truth sets | Newest set's age, median (days) | Median (km) | 90 % (km) | Largest (km) |
|---|---|---|---|---|---|---|
| `AST-E` | LEO | 6 | 0.38 | 1.83 | 7.60 | 12.1 |
| `CPF` | GEO | 6 | 0.32 | 3.61 | 143.3 | 278.8 |
| `CPF` | LEO | 6 | 0.23 | 0.26 | 0.74 | 1.18 |
| `CPF` | MEO | 6 | 0.51 | 1.19 | 2.80 | 2.86 |
| `ISS-E` | LEO | 2 | 0.55 | 0.49 | 0.54 | 0.55 |
| `Kuiper-E` | LEO | 6 | 0.33 | 0.17 | 0.29 | 0.36 |
| `OneWeb-E` | LEO | 6 | 0.54 | 0.27 | 0.50 | 0.65 |
| `Planet-E` | LEO | 6 | 0.29 | 0.54 | 1.39 | 1.57 |
<!-- /measured:newest_set -->

## By the set's age

Every comparison, by orbit class and the set's age at the middle of the six hours.

<!-- measured:by_age -->
| Orbit | Set's age (days) | Comparisons | Objects | Median (km) | 90 % (km) | In track, median (km) | Cross track, median (km) | Radial, median (km) |
|---|---|---|---|---|---|---|---|---|
| GEO | 0–0.5 | 10 | 4 | 2.79 | 8.14 | 0.77 | 2.58 | 0.70 |
| GEO | 0.5–1 | 11 | 4 | 3.20 | 8.60 | 0.68 | 3.04 | 0.77 |
| GEO | 1–2 | 13 | 4 | 3.79 | 10.0 | 1.10 | 3.63 | 0.93 |
| GEO | 2–3 | 19 | 4 | 10.9 | 278.8 | 2.26 | 10.7 | 1.04 |
| GEO | 3–5 | 44 | 5 | 9.61 | 199.6 | 4.83 | 7.07 | 1.30 |
| GEO | 5–7 | 58 | 5 | 12.7 | 279.5 | 7.65 | 7.46 | 1.51 |
| GEO | 7–10 | 71 | 5 | 15.4 | 280.4 | 13.8 | 7.39 | 1.81 |
| LEO | 0–0.5 | 36 | 25 | 0.33 | 1.85 | 0.30 | 0.07 | 0.04 |
| LEO | 0.5–1 | 94 | 31 | 0.42 | 1.40 | 0.40 | 0.07 | 0.05 |
| LEO | 1–2 | 181 | 31 | 1.39 | 9.38 | 1.38 | 0.13 | 0.09 |
| LEO | 2–3 | 156 | 31 | 3.15 | 20.6 | 3.14 | 0.20 | 0.12 |
| LEO | 3–5 | 362 | 31 | 10.7 | 58.0 | 10.7 | 0.23 | 0.20 |
| LEO | 5–7 | 397 | 31 | 14.1 | 110.3 | 14.1 | 0.29 | 0.29 |
| LEO | 7–10 | 524 | 31 | 29.3 | 212.1 | 29.2 | 0.32 | 0.40 |
| MEO | 0–0.5 | 6 | 3 | 0.92 | 2.83 | 0.90 | 0.09 | 0.13 |
| MEO | 0.5–1 | 8 | 4 | 1.19 | 2.75 | 1.00 | 0.12 | 0.33 |
| MEO | 1–2 | 25 | 5 | 1.95 | 2.90 | 1.84 | 0.14 | 0.17 |
| MEO | 2–3 | 7 | 4 | 1.32 | 3.01 | 1.19 | 0.20 | 0.55 |
| MEO | 3–5 | 28 | 5 | 1.52 | 2.06 | 1.18 | 0.23 | 0.28 |
| MEO | 5–7 | 46 | 6 | 1.35 | 2.30 | 1.26 | 0.24 | 0.50 |
| MEO | 7–10 | 43 | 6 | 1.85 | 3.62 | 1.43 | 0.30 | 0.48 |
<!-- /measured:by_age -->

### Low orbits by source

The median and, in brackets, the 90th percentile, in km. The laser-ranging satellites
(`CPF`) in low orbits are geodetic and Earth-observing satellites. The ISS fights
drag. Kuiper, Planet and AST SpaceMobile satellites manoeuvre, Kuiper's while they
raise their orbits.

<!-- measured:leo_by_source -->
| Source | 0–0.5 days | 0.5–1 days | 1–2 days | 2–3 days | 3–5 days | 5–7 days | 7–10 days |
|---|---|---|---|---|---|---|---|
| `AST-E` | 1.25 (6.70) | 1.43 (9.76) | 3.07 (70.5) | 2.90 (100.1) | 20.7 (725.5) | 28.5 (281.6) | 69.6 (653.4) |
| `CPF` | 0.26 (1.06) | 0.30 (0.88) | 0.36 (1.01) | 0.44 (1.74) | 0.58 (26.2) | 0.80 (15.5) | 1.00 (90.6) |
| `ISS-E` | 0.55 (0.55) | 0.43 (0.69) | 3.08 (4.83) | 6.10 (9.81) | 22.8 (34.3) | 16.6 (39.4) | 34.4 (54.4) |
| `Kuiper-E` | 0.21 (1.42) | 0.65 (2.10) | 1.96 (10.8) | 6.04 (21.6) | 29.9 (63.7) | 42.4 (101.6) | 92.7 (391.9) |
| `OneWeb-E` | 0.65 (0.65) | 0.26 (0.43) | 0.79 (2.06) | 1.82 (3.78) | 1.56 (16.1) | 2.72 (33.3) | 9.21 (68.1) |
| `Planet-E` | 0.54 (1.06) | 0.71 (1.78) | 1.39 (8.13) | 4.63 (22.3) | 21.1 (63.7) | 17.8 (130.8) | 28.4 (219.4) |
<!-- /measured:leo_by_source -->

## What the numbers suggest

These are candidates for method 3.0.0, decided in step 6.3 (P6-05), not changes.

1. **A GP set's orbit term grows with its age.** In low orbits, the 90th percentile
   suggests about 2 km below a day, about 10 km at one to two days and about 20 km at
   two to three. Past three days a GP set says little about where a satellite is:
   the median was 10.7 km, and a tenth were more than 58 km off. The follower fetches an open
   request's object at most once per two-hour update (step 5.4), so the newest set is
   usually hours old.
2. **In track and across track separately.** The error is nearly all along the
   track. A term that is larger in track than across it would keep the limit tight
   across the track, where a wrong object in another plane shows, and loose along it,
   where timing and an old set show.
3. **An operator's orbit gets a small term.** SupGP fits its operators' data to about
   0.1 to 0.35 km. How a SupGP set ages is not measured here, since a later truth is
   needed for that. Runs a few days apart give it, before step 6.2 uses SupGP.
4. **Manoeuvres make the tail.** A set from before a manoeuvre is wrong whatever its
   age. No term built from age can know that, which is one more reason for the
   challenge period and for operators' orbits where they exist.
5. **Few of our objects are like Kuiper's.** On 2026-11-23 the allow-list held
   science, education, amateur and CubeSat groups. Many of those satellites cannot
   manoeuvre, but low ones feel drag, as the ISS and Planet's do. These numbers bracket
   them; they do not measure them.

## SCORE's coverage for orbit determination

Step 6.4 fits orbits to observations, which needs the same object seen from several
places, or on several nights, within a few days. A first look on 2026-11-23, at the five
objects SCORE reported as observed most:

| Object | Observations | With a direction | Tracks (3 or more) | Stations | Observers | From | To | Windows of 1, 3, 7 days |
|---|---|---|---|---|---|---|---|---|
| BLUEWALKER 3 (53807) | 855 | 2 | 1 (0) | 1 | 1 | 2026-06-11 | 2026-06-11 | 0, 0, 0 |
| PELICAN 3001 (58296) | 338 | 331 | 3 (3) | 1 | 1 | 2024-05-08 | 2024-06-05 | 0, 0, 0 |
| SPACEMOBILE-002 (61048) | 190 | 190 | 34 (19) | 7 | 5 | 2024-10-20 | 2026-11-05 | 0, 2, 1 |
| SPACEMOBILE-006 (67232) | 287 | 201 | 27 (19) | 4 | 2 | 2026-02-04 | 2026-05-25 | 0, 0, 2 |

- **ACS 3** (59588), the most observed, has 24,463 observations, all from September to
  December 2024. It was too large for one query, and a sample of 1,100 came from one
  observer and one video camera: the one whose PELICAN 3001 tracks step 5.8 replayed.
  Its many nights from one place suit step 6.4's test of predicting the next night.
- **SCORE's 100 most recent observations**, of 19 and 23 November 2026, all came from
  one observer's phone.
- So **windows with two or more stations are rare**: two for SPACEMOBILE-002 within
  three days, and two for SPACEMOBILE-006 within seven.

`orbit-watch score-coverage` counts this from files written by `fetch-score`. A station
here is one instrument and set of observers at one place to about a kilometre; a
window counts when tracks from two or more stations, three of them with three or more
observations each, begin within the span.

## Reproduce

From the repository's `core` directory:

```sh
orbit-watch measure-reference-orbits --fetch   # fetch a new run, then measure it
orbit-watch measure-reference-orbits           # measure the newest run in the cache again
```

`--fetch` downloads one SupGP file per source from CelesTrak and makes one request per
object to SatChecker, two seconds apart. It refuses to start within two hours of the
last run, since CelesTrak asks for that much between SupGP downloads. The first
answer that is not 200 stops the run, and an incomplete run is never used.

Without `--fetch` the newest run in the cache (`~/.cache/orbit-watch/reference-accuracy/`,
or `$ORBIT_WATCH_CACHE`) is measured again, and gives these files byte for byte.
SupGP keeps no history, so nobody can fetch the same truth again later. A new run
measures the same way with the sets current then. `--check` tells whether the files
match a run.
