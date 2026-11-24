# Reference orbits measured against operators' orbits

How far are CelesTrak's GP element sets from where the satellites really are, and how
does that grow with a set's age? Step 6.1 of phase 6 measures it before method 3.0.0
changes the limit's orbit term
([P6-02](decisions.md#p6-02-measure-first-again),
[D-60](decisions.md#d-60-reference-orbits-measured-against-operators-orbits)). Step 6.2
adds how operators' own orbits age
([D-61](decisions.md#d-61-how-operators-orbits-age)).

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
  have had, a median 0.2 to 0.6 days old, was a median 0.12 to 0.78 km off for AST
  SpaceMobile, Kuiper, OneWeb, the ISS, Planet and the laser-ranging satellites in low
  orbits. Its 90th percentile was below 1.2 km, except AST SpaceMobile's: 3.8 km, and
  7.3 km at most. In the first run, eight hours earlier, AST SpaceMobile's median was
  1.83 km: its satellites manoeuvre, and one run is a snapshot.
- **In low orbits the error grows fast with the set's age, and along the track.** Over
  all low-orbit objects, the median was 0.28 km for sets under half a day old, 1.5 km
  at one to two days, 3.4 km at two to three, 10.1 km at three to five and 33 km at
  seven to ten. The 90th percentile was 0.9, 8.9, 27, 63 and 239 km. Nearly all of it is
  in track; the median cross-track and radial parts stay at 0.4 km or less.
- **How fast depends on the object.** The passive laser-ranging satellites stay near
  their fresh error: from 0.26 km to 1.0 km, the median, over ten days. The ISS, which
  fights drag and is reboosted, reaches 3 km at one to two days. Satellites that
  manoeuvre reach tens of kilometres within three to five days, and hundreds at the
  90th percentile after five: Kuiper's, Planet's, which keep their places by drag, and
  AST SpaceMobile's.
- **Medium orbits change slowly**: a median of 0.2 to 2.0 km over ten days. Six
  navigation satellites in geosynchronous orbits, of QZSS and NavIC, were 3 to 16 km
  off, the median, and up to 285 km, most likely after a manoeuvre.
- **The truth has its own error.** CelesTrak fitted the SupGP sets to the operators'
  data to a median of 0.12 to 0.35 km, so smaller differences cannot be told apart from
  SupGP's own.
- **An operator's set a few hours to a day old was a median 0.1 to 0.9 km from a later
  one**, and closer than the newest GP set of its time in 18 of 30 pairs, against 10.
  It was closer for every laser-ranging satellite in medium and geosynchronous orbits.
  In low orbits the two were alike, and manoeuvres still made the tail: two of AST
  SpaceMobile's satellites were 14 and 19 km off after half a day.

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
    behind them had been posted on 2026-11-23, so the run of 2026-11-24 had three.
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
Run fetched 2026-11-24T04:46:16Z: 45 truth sets of 43 objects, 2190 comparisons with GP sets, 0 not propagated, 3 left out as the truth itself.
<!-- /measured:run -->

### The sources

<!-- measured:sources -->
| Source | Objects | Truth sets | SupGP's own fit, median (km) | GP sets compared |
|---|---|---|---|---|
| `AST-E` | 6 | 6 | 0.24 | 298 |
| `CPF` | 18 | 18 | 0.32 | 658 |
| `ISS-E` | 1 | 3 | 0.12 | 143 |
| `Kuiper-E` | 6 | 6 | 0.25 | 326 |
| `OneWeb-E` | 6 | 6 | 0.25 | 342 |
| `Planet-E` | 6 | 6 | 0.35 | 423 |
<!-- /measured:sources -->

## The set a service would use

For each truth, the newest GP set at or before its epoch: the set that the service's
follower would have had (step 5.4).

<!-- measured:newest_set -->
| Source | Orbit | Truth sets | Newest set's age, median (days) | Median (km) | 90 % (km) | Largest (km) |
|---|---|---|---|---|---|---|
| `AST-E` | LEO | 6 | 0.38 | 0.20 | 3.84 | 7.32 |
| `CPF` | GEO | 6 | 0.23 | 2.97 | 5.51 | 7.81 |
| `CPF` | LEO | 6 | 0.23 | 0.26 | 0.74 | 1.18 |
| `CPF` | MEO | 6 | 0.71 | 1.54 | 1.97 | 2.03 |
| `ISS-E` | LEO | 3 | 0.41 | 0.78 | 1.12 | 1.20 |
| `Kuiper-E` | LEO | 6 | 0.33 | 0.12 | 0.32 | 0.51 |
| `OneWeb-E` | LEO | 6 | 0.54 | 0.31 | 0.82 | 1.15 |
| `Planet-E` | LEO | 6 | 0.29 | 0.39 | 0.85 | 1.01 |
<!-- /measured:newest_set -->

## By the set's age

Every comparison, by orbit class and the set's age at the middle of the six hours.

<!-- measured:by_age -->
| Orbit | Set's age (days) | Comparisons | Objects | Median (km) | 90 % (km) | In track, median (km) | Cross track, median (km) | Radial, median (km) |
|---|---|---|---|---|---|---|---|---|
| GEO | 0–0.5 | 11 | 5 | 2.80 | 8.14 | 0.78 | 2.57 | 0.72 |
| GEO | 0.5–1 | 11 | 4 | 3.20 | 8.60 | 0.68 | 3.04 | 0.77 |
| GEO | 1–2 | 13 | 4 | 3.79 | 10.0 | 1.10 | 3.63 | 0.93 |
| GEO | 2–3 | 15 | 3 | 10.8 | 11.6 | 2.08 | 10.6 | 1.03 |
| GEO | 3–5 | 46 | 5 | 9.64 | 282.9 | 4.90 | 7.09 | 1.31 |
| GEO | 5–7 | 54 | 5 | 11.6 | 283.7 | 7.64 | 7.39 | 1.50 |
| GEO | 7–10 | 72 | 5 | 15.5 | 285.1 | 13.9 | 7.39 | 1.83 |
| LEO | 0–0.5 | 35 | 24 | 0.28 | 0.92 | 0.23 | 0.07 | 0.05 |
| LEO | 0.5–1 | 89 | 31 | 0.35 | 2.59 | 0.30 | 0.07 | 0.05 |
| LEO | 1–2 | 173 | 31 | 1.51 | 8.87 | 1.50 | 0.13 | 0.08 |
| LEO | 2–3 | 196 | 31 | 3.36 | 26.8 | 3.35 | 0.20 | 0.13 |
| LEO | 3–5 | 334 | 31 | 10.1 | 62.8 | 10.1 | 0.24 | 0.20 |
| LEO | 5–7 | 398 | 31 | 17.8 | 113.4 | 17.8 | 0.34 | 0.29 |
| LEO | 7–10 | 567 | 31 | 33.3 | 238.5 | 33.3 | 0.40 | 0.40 |
| MEO | 0–0.5 | 3 | 2 | 0.17 | 1.41 | 0.16 | 0.06 | 0.02 |
| MEO | 0.5–1 | 10 | 5 | 1.61 | 2.03 | 1.47 | 0.10 | 0.31 |
| MEO | 1–2 | 13 | 6 | 1.74 | 2.21 | 1.51 | 0.13 | 0.15 |
| MEO | 2–3 | 23 | 5 | 1.97 | 2.74 | 1.89 | 0.15 | 0.39 |
| MEO | 3–5 | 28 | 5 | 1.42 | 2.28 | 1.23 | 0.21 | 0.22 |
| MEO | 5–7 | 37 | 6 | 1.40 | 2.81 | 1.09 | 0.26 | 0.68 |
| MEO | 7–10 | 42 | 6 | 1.86 | 3.37 | 1.77 | 0.31 | 0.34 |
<!-- /measured:by_age -->

### Low orbits by source

The median and, in brackets, the 90th percentile, in km. The laser-ranging satellites
(`CPF`) in low orbits are geodetic and Earth-observing satellites. The ISS fights
drag. Kuiper, Planet and AST SpaceMobile satellites manoeuvre, Kuiper's while they
raise their orbits.

<!-- measured:leo_by_source -->
| Source | 0–0.5 days | 0.5–1 days | 1–2 days | 2–3 days | 3–5 days | 5–7 days | 7–10 days |
|---|---|---|---|---|---|---|---|
| `AST-E` | 0.20 (3.84) | 2.00 (19.3) | 2.58 (47.7) | 5.25 (190.7) | 10.9 (651.5) | 33.3 (516.6) | 62.2 (705.9) |
| `CPF` | 0.26 (1.06) | 0.30 (0.88) | 0.36 (1.01) | 0.44 (1.74) | 0.58 (26.2) | 0.80 (15.5) | 1.00 (90.6) |
| `ISS-E` | 0.55 (0.71) | 0.47 (0.80) | 3.08 (5.13) | 6.42 (10.6) | 20.6 (37.9) | 19.2 (37.4) | 35.9 (52.6) |
| `Kuiper-E` | 0.13 (0.36) | 0.38 (2.98) | 1.65 (12.4) | 4.67 (27.1) | 26.4 (67.9) | 47.0 (105.9) | 93.5 (366.1) |
| `OneWeb-E` | – | 0.25 (0.46) | 1.46 (2.52) | 1.83 (3.63) | 2.46 (18.3) | 2.93 (33.5) | 9.09 (73.1) |
| `Planet-E` | 0.59 (0.85) | 1.02 (1.97) | 1.39 (8.87) | 5.28 (22.6) | 23.0 (72.5) | 20.9 (123.8) | 31.8 (238.5) |
<!-- /measured:leo_by_source -->

## How operators' orbits age

Step 6.2 lets verification use an operator's orbit
([P6-03](decisions.md#p6-03-operators-orbits-from-celestraks-supgp),
[D-61](decisions.md#d-61-how-operators-orbits-age)). The set it would use is the one
published by then, so it is a prediction some hours or a day old. With two runs in the
cache, each truth of the later run is compared, as above, with:

- **the operator's set of the earlier run** with the latest epoch at or before the
  truth's: the set a service holding the earlier run's sets would use for that time.
  The ISS's ephemeris gives segments ahead, so its set may not have begun by the
  earlier run;
- **the newest GP set of the same time**: the one with the latest epoch among those
  SatChecker had collected by the earlier run. SatChecker's `date_collected` stands for
  when a service could have had it.

<!-- measured:ageing_run -->
Runs fetched 2026-11-23T21:05:00Z, 2026-11-24T04:46:16Z: 30 pairs of an operator's set and a later one, 15 sets unchanged between the runs.
<!-- /measured:ageing_run -->

<!-- measured:operator_by_age -->
| Source | Orbit | Set's age (days) | Pairs | Objects | Median (km) | 90 % (km) | Largest (km) | In track, median (km) | Cross track, median (km) |
|---|---|---|---|---|---|---|---|---|---|
| `AST-E` | LEO | 0.5–1 | 6 | 6 | 0.30 | 16.5 | 19.1 | 0.30 | 0.04 |
| `CPF` | GEO | 1–2 | 2 | 2 | 0.90 | 0.97 | 0.99 | 0.80 | 0.27 |
| `CPF` | MEO | 1–2 | 5 | 5 | 0.28 | 0.40 | 0.47 | 0.27 | 0.04 |
| `Kuiper-E` | LEO | 0–0.5 | 4 | 4 | 0.11 | 0.43 | 0.56 | 0.11 | 0.02 |
| `Kuiper-E` | LEO | 0.5–1 | 2 | 2 | 0.18 | 0.25 | 0.27 | 0.16 | 0.06 |
| `OneWeb-E` | LEO | 0.5–1 | 5 | 5 | 0.34 | 0.43 | 0.48 | 0.34 | 0.02 |
| `Planet-E` | LEO | 0–0.5 | 5 | 5 | 0.28 | 1.19 | 1.63 | 0.28 | 0.02 |
| `Planet-E` | LEO | 0.5–1 | 1 | 1 | 0.86 | 0.86 | 0.86 | 0.86 | 0.04 |
<!-- /measured:operator_by_age -->

The two side by side, for the pairs that had a GP set of the same time:

<!-- measured:operator_against_gp -->
| Source | Orbit | Pairs | Operator's set closer | GP set closer | Operator's set: age, median (days) | Median (km) | Newest GP set: age, median (days) | Median (km) |
|---|---|---|---|---|---|---|---|---|
| `AST-E` | LEO | 6 | 3 | 3 | 0.50 | 0.30 | 0.75 | 2.33 |
| `CPF` | GEO | 2 | 2 | 0 | 1.12 | 0.90 | 3.77 | 143.0 |
| `CPF` | MEO | 5 | 5 | 0 | 1.11 | 0.28 | 0.99 | 1.86 |
| `Kuiper-E` | LEO | 6 | 3 | 3 | 0.43 | 0.11 | 0.69 | 0.17 |
| `OneWeb-E` | LEO | 5 | 1 | 2 | 0.57 | 0.34 | 0.60 | 0.25 |
| `Planet-E` | LEO | 6 | 4 | 2 | 0.46 | 0.41 | 0.62 | 0.77 |
<!-- /measured:operator_against_gp -->

- **Operators' sets hold for a day.** For Kuiper, OneWeb, Planet and the
  laser-ranging satellites in medium orbits, a set a few hours to a day old was a
  median 0.11 to 0.86 km from the later one. That is near SupGP's own fit, so much
  of it may be the fit, not the ageing.
- **Where GP is weakest, the operator's set is far better.** For the laser-ranging
  satellites in medium and geosynchronous orbits the operator's set was closer in all
  seven pairs: a median 0.28 km against 1.86 km in medium orbits, though a little
  older, and 0.8 and 1.0 km against 283 and 3.2 km for the two in geosynchronous
  orbits.
- **In low orbits it is a draw.** The operator's set was closer in 11 of 23 pairs and
  the GP set in 10. Two OneWeb pairs were ties: the GP set had the operator's set's
  epoch and, to the metre, its difference from the truth, so CelesTrak's GP for these
  satellites most likely came from OneWeb's own data. The medians favour the
  operator's set for AST SpaceMobile, Kuiper and Planet, and the GP set for OneWeb.
- **Manoeuvres still make the tail.** Two of AST SpaceMobile's six were 14 and 19 km
  off after half a day. A prediction cannot know a manoeuvre that was decided after it.
- **The ISS's sets did not change.** NASA's ephemeris gives its six-hour segments two
  weeks ahead, and the later run held the same segments as the earlier one.
- **The truth is the same kind of set.** A later operator's set shares its operator's
  way of fitting, so this comparison may favour the operator's earlier set a little.
- **Only up to a day is measured.** These two runs were eight hours apart. A run some
  days later gives longer ages, before verification uses an operator's set.

## What the numbers suggest

These are candidates for method 3.0.0, decided in step 6.3 (P6-05), not changes.

1. **A GP set's orbit term grows with its age.** In low orbits, the 90th percentile
   suggests about 1 to 3 km below a day, about 9 km at one to two days and about 27 km
   at two to three. Past three days a GP set says little about where a satellite is:
   the median was 10.1 km, and a tenth were more than 63 km off. The follower fetches an open
   request's object at most once per two-hour update (step 5.4), so the newest set is
   usually hours old.
2. **In track and across track separately.** The error is nearly all along the
   track. A term that is larger in track than across it would keep the limit tight
   across the track, where a wrong object in another plane shows, and loose along it,
   where timing and an old set show.
3. **An operator's orbit gets a small term.** SupGP fits its operators' data to about
   0.1 to 0.35 km, and a set up to a day old was a median 0.1 to 0.9 km from a later
   one ([How operators' orbits age](#how-operators-orbits-age)). How it ages over
   longer is not measured yet.
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
or `$ORBIT_WATCH_CACHE`) is measured again, with the runs before it for how operators'
orbits age, and gives these files byte for byte.
SupGP keeps no history, so nobody can fetch the same truth again later. A new run
measures the same way with the sets current then. `--check` tells whether the files
match a run.
