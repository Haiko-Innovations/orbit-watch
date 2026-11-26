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
  have had, a median 0.2 to 0.6 days old, was a median 0.13 to 0.84 km off for AST
  SpaceMobile, Kuiper, OneWeb, Planet and the laser-ranging satellites in low orbits,
  and 2.5 km for the ISS. Its 90th percentile was below 0.5 km for Kuiper and Planet,
  but 4 to 22 km for the others, whose six objects held a manoeuvre or two. One run is a
  snapshot: AST SpaceMobile's median was 1.83, 0.20 and 0.13 km in the three runs.
- **In low orbits the error grows fast with the set's age, and along the track.** Over
  all low-orbit objects, the median was 0.5 to 0.9 km for sets under a day old, 1.3 km
  at one to two days, 3.7 km at two to three, 10.2 km at three to five and 39 km at
  seven to ten. The 90th percentile was about 3, 8, 16, 56 and 194 km. Nearly all of it
  is in track; the median cross-track and radial parts stay at 0.5 km or less.
- **How fast depends on the object.** The passive laser-ranging satellites stay near
  their fresh error: from 0.25 km to 1.1 km, the median, over ten days. The ISS, which
  fights drag and is reboosted, reaches 4 km at two to three days. Satellites that
  manoeuvre reach ten kilometres or more within three to five days, and hundreds at the
  90th percentile after five: Kuiper's, Planet's, which keep their places by drag, and
  AST SpaceMobile's.
- **Medium orbits change slowly**: a median of 0.1 to 3 km over ten days in all but one
  age bin. Five navigation satellites in geosynchronous orbits, of QZSS and NavIC, were
  2 to 22 km off, the median, and up to 298 km, most likely after a manoeuvre.
- **The truth has its own error.** CelesTrak fitted the SupGP sets to the operators'
  data to a median of 0.11 to 0.37 km, so smaller differences cannot be told apart from
  SupGP's own.
- **An operator's set a few hours to a day old was a median 0.1 to 0.9 km from a later
  one.** Two to three days old, the laser-ranging satellites' were still 0.2 to 1.6 km
  off, but those of satellites that manoeuvre were 3 to 9 km off, no better than a GP
  set of that age. Against the newest GP set of its time the operator's set was closer
  in 72 of 112 pairs, against 31, and in 39 of the laser-ranging satellites' 41.

- **Across the track the error stays small in low and medium orbits.** For GP sets up to
  three days old in low orbits, the 90th percentile across the track was 0.17 to 0.48 km
  and radially 0.10 to 0.24 km, against 2.7 to 16 km along it; in medium orbits 0.13 to
  0.24 km across it up to five days. In geosynchronous orbits it was 4.2 to 6.6 km across
  the track, as large as along it.
- **A track shifted in time, against the sets a service could have used**: with sets under a
  day old, every good track of Kuiper, OneWeb and Planet passed and none a second late;
  at two to three days, the method's 5 km rejected half the good tracks of satellites
  that manoeuvre against operators' sets, and 29 of 46 against GP sets
  ([Time shifts](#time-shifts-against-operators-orbits)).

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
    behind them had been posted on 2026-11-23, so the runs of 2026-11-24 and 2026-11-26
    had three and eight.
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
Run fetched 2026-11-26T08:25:19Z: 50 truth sets of 43 objects, 2335 comparisons with GP sets, 0 not propagated, 12 left out as the truth itself.
<!-- /measured:run -->

### The sources

<!-- measured:sources -->
| Source | Objects | Truth sets | SupGP's own fit, median (km) | GP sets compared |
|---|---|---|---|---|
| `AST-E` | 6 | 6 | 0.25 | 282 |
| `CPF` | 18 | 18 | 0.33 | 639 |
| `ISS-E` | 1 | 8 | 0.11 | 375 |
| `Kuiper-E` | 6 | 6 | 0.24 | 311 |
| `OneWeb-E` | 6 | 6 | 0.26 | 318 |
| `Planet-E` | 6 | 6 | 0.37 | 410 |
<!-- /measured:sources -->

## The set a service would use

For each truth, the newest GP set at or before its epoch: the set that the service's
follower would have had (step 5.4).

<!-- measured:newest_set -->
| Source | Orbit | Truth sets | Newest set's age, median (days) | Median (km) | 90 % (km) | Largest (km) |
|---|---|---|---|---|---|---|
| `AST-E` | LEO | 6 | 0.50 | 0.13 | 22.4 | 38.5 |
| `CPF` | GEO | 6 | 0.21 | 3.98 | 4.29 | 4.36 |
| `CPF` | LEO | 6 | 0.32 | 0.25 | 3.97 | 7.65 |
| `CPF` | MEO | 6 | 0.58 | 0.72 | 2.93 | 3.13 |
| `ISS-E` | LEO | 8 | 0.35 | 2.46 | 4.43 | 4.44 |
| `Kuiper-E` | LEO | 6 | 0.32 | 0.16 | 0.38 | 0.39 |
| `OneWeb-E` | LEO | 6 | 0.43 | 0.84 | 17.6 | 33.9 |
| `Planet-E` | LEO | 6 | 0.36 | 0.26 | 0.43 | 0.50 |
<!-- /measured:newest_set -->

## By the set's age

Every comparison, by orbit class and the set's age at the middle of the six hours.

<!-- measured:by_age -->
| Orbit | Set's age (days) | Comparisons | Objects | Median (km) | 90 % (km) | In track, median (90 %) (km) | Cross track, median (90 %) (km) | Radial, median (90 %) (km) |
|---|---|---|---|---|---|---|---|---|
| GEO | 0–0.5 | 12 | 5 | 4.02 | 4.58 | 1.67 (3.66) | 2.26 (4.21) | 0.85 (1.57) |
| GEO | 0.5–1 | 13 | 5 | 2.23 | 4.73 | 1.48 (3.37) | 0.79 (4.44) | 0.94 (1.62) |
| GEO | 1–2 | 20 | 5 | 5.07 | 5.59 | 1.35 (4.81) | 0.77 (5.18) | 1.12 (1.84) |
| GEO | 2–3 | 25 | 5 | 6.58 | 7.62 | 2.60 (7.13) | 1.02 (6.61) | 1.39 (2.23) |
| GEO | 3–5 | 34 | 4 | 9.42 | 11.7 | 5.07 (11.4) | 7.36 (8.43) | 1.59 (2.63) |
| GEO | 5–7 | 41 | 5 | 15.0 | 295.4 | 12.4 (112.4) | 9.61 (273.0) | 2.58 (4.50) |
| GEO | 7–10 | 68 | 5 | 22.0 | 298.0 | 19.6 (119.4) | 11.6 (273.0) | 3.06 (4.75) |
| LEO | 0–0.5 | 41 | 19 | 0.86 | 2.68 | 0.85 (2.67) | 0.10 (0.17) | 0.06 (0.10) |
| LEO | 0.5–1 | 76 | 26 | 0.52 | 3.48 | 0.51 (3.48) | 0.06 (0.23) | 0.05 (0.16) |
| LEO | 1–2 | 146 | 30 | 1.30 | 8.07 | 1.29 (8.07) | 0.14 (0.32) | 0.09 (0.17) |
| LEO | 2–3 | 182 | 30 | 3.69 | 16.0 | 3.69 (16.0) | 0.23 (0.48) | 0.13 (0.24) |
| LEO | 3–5 | 427 | 31 | 10.2 | 55.6 | 10.2 (55.6) | 0.33 (0.69) | 0.19 (0.54) |
| LEO | 5–7 | 372 | 31 | 32.4 | 127.6 | 32.4 (127.6) | 0.38 (0.99) | 0.32 (1.49) |
| LEO | 7–10 | 682 | 31 | 38.8 | 194.2 | 38.7 (194.2) | 0.53 (1.29) | 0.43 (3.14) |
| MEO | 0–0.5 | 3 | 2 | 0.09 | 2.52 | 0.05 (2.43) | 0.07 (0.13) | 0.02 (0.64) |
| MEO | 0.5–1 | 13 | 5 | 1.08 | 3.49 | 1.03 (3.39) | 0.15 (0.17) | 0.29 (0.81) |
| MEO | 1–2 | 9 | 3 | 2.99 | 3.94 | 2.90 (3.85) | 0.14 (0.15) | 0.72 (0.86) |
| MEO | 2–3 | 19 | 6 | 1.02 | 4.61 | 0.94 (4.50) | 0.14 (0.20) | 0.33 (0.99) |
| MEO | 3–5 | 26 | 6 | 0.87 | 5.54 | 0.80 (5.43) | 0.14 (0.24) | 0.32 (1.11) |
| MEO | 5–7 | 23 | 3 | 5.86 | 6.59 | 5.74 (6.47) | 0.21 (0.23) | 1.17 (1.25) |
| MEO | 7–10 | 62 | 6 | 2.62 | 8.23 | 2.59 (8.10) | 0.30 (0.36) | 0.41 (1.40) |
<!-- /measured:by_age -->

### Low orbits by source

The median and, in brackets, the 90th percentile, in km. The laser-ranging satellites
(`CPF`) in low orbits are geodetic and Earth-observing satellites. The ISS fights
drag. Kuiper, Planet and AST SpaceMobile satellites manoeuvre, Kuiper's while they
raise their orbits.

<!-- measured:leo_by_source -->
| Source | 0–0.5 days | 0.5–1 days | 1–2 days | 2–3 days | 3–5 days | 5–7 days | 7–10 days |
|---|---|---|---|---|---|---|---|
| `AST-E` | 0.06 (0.06) | 0.52 (15.9) | 3.04 (24.4) | 6.30 (120.0) | 12.7 (629.0) | 19.8 (1,494.3) | 70.2 (922.9) |
| `CPF` | 0.25 (0.28) | 0.14 (0.14) | 0.32 (7.65) | 0.42 (6.99) | 0.55 (4.29) | 0.80 (37.9) | 1.08 (38.9) |
| `ISS-E` | 2.29 (3.90) | 2.51 (3.34) | 1.13 (4.17) | 4.31 (11.4) | 20.3 (32.0) | 48.1 (80.1) | 37.1 (66.1) |
| `Kuiper-E` | 0.16 (0.38) | 0.32 (4.42) | 2.36 (16.9) | 4.24 (11.1) | 11.4 (56.2) | 47.6 (158.1) | 103.7 (253.4) |
| `OneWeb-E` | 1.34 (54.3) | 0.62 (1.59) | 1.80 (3.07) | 2.73 (53.5) | 3.64 (55.4) | 5.63 (54.0) | 17.7 (83.8) |
| `Planet-E` | 0.41 (0.61) | 0.37 (0.63) | 0.92 (4.88) | 6.42 (21.9) | 14.7 (60.4) | 52.8 (195.1) | 51.2 (216.4) |
<!-- /measured:leo_by_source -->

## How operators' orbits age

Step 6.2 lets verification use an operator's orbit
([P6-03](decisions.md#p6-03-operators-orbits-from-celestraks-supgp),
[D-61](decisions.md#d-61-how-operators-orbits-age)). The set it would use is the one
published by then, so it is a prediction some hours or days old. With several runs in the
cache, each truth of a later run is compared, as above, with:

- **the operator's set of the earlier run** with the latest epoch at or before the
  truth's: the set a service holding the earlier run's sets would use for that time.
  The ISS's ephemeris gives segments ahead, so its set may not have begun by the
  earlier run;
- **the newest GP set of the same time**: the one with the latest epoch among those
  SatChecker had collected by the earlier run. SatChecker's `date_collected` stands for
  when a service could have had it.

<!-- measured:ageing_run -->
Runs fetched 2026-11-23T21:05:00Z, 2026-11-24T04:46:16Z, 2026-11-26T08:25:19Z: 112 pairs of an operator's set and a later one, 31 sets unchanged between the runs.
<!-- /measured:ageing_run -->

<!-- measured:operator_by_age -->
| Source | Orbit | Set's age (days) | Pairs | Objects | Median (km) | 90 % (km) | Largest (km) | In track, median (90 %) (km) | Cross track, median (90 %) (km) |
|---|---|---|---|---|---|---|---|---|---|
| `AST-E` | LEO | 0.5–1 | 6 | 6 | 0.30 | 16.5 | 19.1 | 0.30 (16.4) | 0.04 (0.11) |
| `AST-E` | LEO | 2–3 | 12 | 6 | 9.05 | 458.1 | 606.0 | 9.04 (457.9) | 0.23 (0.31) |
| `CPF` | GEO | 1–2 | 2 | 2 | 0.90 | 0.97 | 0.99 | 0.80 (0.88) | 0.27 (0.35) |
| `CPF` | GEO | 2–3 | 7 | 5 | 1.64 | 2.80 | 2.80 | 1.42 (2.61) | 0.39 (1.37) |
| `CPF` | GEO | 3–5 | 3 | 3 | 2.37 | 3.62 | 3.93 | 1.67 (1.96) | 1.11 (3.06) |
| `CPF` | LEO | 2–3 | 10 | 5 | 0.22 | 1.37 | 1.37 | 0.17 (1.37) | 0.09 (0.12) |
| `CPF` | LEO | 3–5 | 2 | 1 | 0.28 | 0.28 | 0.28 | 0.23 (0.23) | 0.13 (0.13) |
| `CPF` | MEO | 1–2 | 5 | 5 | 0.28 | 0.40 | 0.47 | 0.27 (0.39) | 0.04 (0.11) |
| `CPF` | MEO | 2–3 | 7 | 6 | 0.38 | 0.60 | 0.64 | 0.26 (0.56) | 0.10 (0.14) |
| `CPF` | MEO | 3–5 | 5 | 5 | 0.78 | 0.87 | 0.89 | 0.70 (0.80) | 0.16 (0.20) |
| `Kuiper-E` | LEO | 0–0.5 | 4 | 4 | 0.11 | 0.43 | 0.56 | 0.11 (0.42) | 0.02 (0.03) |
| `Kuiper-E` | LEO | 0.5–1 | 2 | 2 | 0.18 | 0.25 | 0.27 | 0.16 (0.24) | 0.06 (0.06) |
| `Kuiper-E` | LEO | 2–3 | 12 | 6 | 4.92 | 16.3 | 57.2 | 4.91 (16.3) | 0.23 (0.27) |
| `OneWeb-E` | LEO | 0.5–1 | 5 | 5 | 0.34 | 0.43 | 0.48 | 0.34 (0.43) | 0.02 (0.04) |
| `OneWeb-E` | LEO | 2–3 | 12 | 6 | 3.22 | 76.6 | 132.6 | 3.22 (76.6) | 0.11 (0.17) |
| `Planet-E` | LEO | 0–0.5 | 5 | 5 | 0.28 | 1.19 | 1.63 | 0.28 (1.19) | 0.02 (0.02) |
| `Planet-E` | LEO | 0.5–1 | 1 | 1 | 0.86 | 0.86 | 0.86 | 0.86 (0.86) | 0.04 (0.04) |
| `Planet-E` | LEO | 1–2 | 1 | 1 | 4.44 | 4.44 | 4.44 | 4.44 (4.44) | 0.04 (0.04) |
| `Planet-E` | LEO | 2–3 | 11 | 6 | 7.28 | 11.7 | 34.1 | 7.27 (11.7) | 0.07 (0.11) |
<!-- /measured:operator_by_age -->

The two side by side, for the pairs that had a GP set of the same time:

<!-- measured:operator_against_gp -->
| Source | Orbit | Pairs | Operator's set closer | GP set closer | Operator's set: age, median (days) | Median (km) | Newest GP set: age, median (days) | Median (km) |
|---|---|---|---|---|---|---|---|---|
| `AST-E` | LEO | 18 | 10 | 8 | 2.25 | 7.84 | 2.50 | 6.33 |
| `CPF` | GEO | 12 | 12 | 0 | 2.12 | 1.60 | 2.45 | 4.20 |
| `CPF` | LEO | 12 | 12 | 0 | 2.12 | 0.24 | 1.58 | 0.37 |
| `CPF` | MEO | 17 | 15 | 2 | 2.12 | 0.38 | 2.55 | 1.05 |
| `Kuiper-E` | LEO | 18 | 8 | 9 | 2.30 | 1.78 | 2.50 | 5.23 |
| `OneWeb-E` | LEO | 17 | 5 | 4 | 2.25 | 2.23 | 2.26 | 2.43 |
| `Planet-E` | LEO | 18 | 10 | 8 | 2.17 | 3.42 | 2.37 | 4.47 |
<!-- /measured:operator_against_gp -->

- **Operators' sets hold for a day.** For Kuiper, OneWeb, Planet and the
  laser-ranging satellites in medium orbits, a set a few hours to a day old was a
  median 0.11 to 0.86 km from the later one. That is near SupGP's own fit, so much
  of it may be the fit, not the ageing.
- **Then those of satellites that manoeuvre age like GP.** Two to three days old, AST
  SpaceMobile's, Kuiper's, OneWeb's and Planet's were a median 3.2 to 9.1 km off, and
  AST SpaceMobile's 90th percentile was 458 km; the GP sets of all low orbits at that age
  were 3.7 km. Against the newest GP set of the same time, a median 2.2 to 2.5 days old,
  the operator's set was closer in 33 of their 71 pairs and the GP set in 29.
- **The laser-ranging satellites' hold for days.** Their predictions were 0.2 to 1.6 km
  off at two to three days, and 0.3 to 2.4 km at three to five. Against the newest GP
  set of the same time the operator's set was closer in 39 of 41 pairs, in low, medium
  and geosynchronous orbits.
- **Ties.** In 9 pairs neither was closer by a metre. In 8 of them, 7 OneWeb's and one
  Kuiper's, the GP set had the operator's set's epoch: CelesTrak's GP for these
  satellites most likely comes from the operators' own data.
- **Manoeuvres still make the tail.** Two of AST SpaceMobile's six were 14 and 19 km
  off after half a day. A prediction cannot know a manoeuvre that was decided after it.
- **The ISS's sets did not change.** NASA's ephemeris gives its six-hour segments two
  weeks ahead, and the later runs held the same segments as the earlier ones.
- **The truth is the same kind of set.** A later operator's set shares its operator's
  way of fitting, so this comparison may favour the operator's earlier set a little.
- **So verification uses an operator's set up to a day old, and a laser-ranging
  prediction up to three days old** ([D-66](decisions.md#d-66-verification-uses-the-operators-orbit)).
  Older, the GP sets verify as before. The three runs were 8 hours and 2.2 days apart.

## Time shifts against operators' orbits

Step 5.3 found that against GP sets in low orbits a track half a second late passes and one
a second late does not
([D-46](decisions.md#d-46-the-method-measured-on-real-data)). Here the same question is
asked of the two sets a service could have used for each pair above
([D-67](decisions.md#d-67-the-measurement-for-method-300)):

- **the track** is made from the truth, the later operator's set: what a station directly
  under the satellite would see over one minute, an hour after the truth's epoch, 31
  positions with 10″ of noise, each declared to 10″ and 0.01 s. It is made in memory and
  never written;
- **it is shifted** later by each of the times below and verified with method 2.1.0, its
  fixed 5 km, and with method 3.0.0, its orbit term by the set's kind and age
  ([D-68](decisions.md#d-68-method-300)), against the earlier operator's set and against
  the newest GP set of the same time;
- **each cell counts the tracks that passed** the residual check. At 0 s every track should
  pass; past it, a pass is a false acceptance. A track that did not pass failed, or with
  method 3.0.0 was inconclusive: past its set's ages.

<!-- measured:shift_run -->
224 pairs of a track and a set, of 31 positions each, verified with methods 2.1.0 and 3.0.0 at 8 shifts.
<!-- /measured:shift_run -->

<!-- measured:time_shifts -->
| Method | Source | Orbit | Reference | Set's age (days) | Tracks | 0 s | 0.25 s | 0.5 s | 1 s | 2 s | 5 s | 10 s | 30 s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2.1.0 | `AST-E` | LEO | Operator's set | 0–1 | 6 | 4 | 4 | 5 | 2 | 1 | 0 | 0 | 0 |
| 2.1.0 | `AST-E` | LEO | Operator's set | 2–3 | 12 | 3 | 3 | 4 | 4 | 0 | 0 | 0 | 0 |
| 2.1.0 | `AST-E` | LEO | Newest GP set | 0–1 | 6 | 5 | 4 | 4 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `AST-E` | LEO | Newest GP set | 2–3 | 12 | 3 | 3 | 1 | 2 | 3 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | GEO | Operator's set | 1–2 | 2 | 2 | 2 | 2 | 2 | 1 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | GEO | Operator's set | 2–3 | 7 | 7 | 7 | 7 | 7 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | GEO | Operator's set | 3–10 | 3 | 3 | 3 | 3 | 3 | 1 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | GEO | Newest GP set | 0–1 | 4 | 4 | 4 | 4 | 2 | 2 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | GEO | Newest GP set | 2–3 | 3 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | GEO | Newest GP set | 3–10 | 5 | 3 | 3 | 3 | 3 | 1 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | LEO | Operator's set | 2–3 | 10 | 10 | 10 | 10 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | LEO | Operator's set | 3–10 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | LEO | Newest GP set | 0–1 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | LEO | Newest GP set | 1–2 | 8 | 6 | 6 | 8 | 2 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | LEO | Newest GP set | 3–10 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Operator's set | 1–2 | 5 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Operator's set | 2–3 | 7 | 7 | 7 | 7 | 5 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Operator's set | 3–10 | 5 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Newest GP set | 0–1 | 3 | 3 | 3 | 3 | 3 | 2 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Newest GP set | 1–2 | 4 | 4 | 4 | 4 | 2 | 1 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Newest GP set | 2–3 | 7 | 7 | 7 | 7 | 3 | 0 | 0 | 0 | 0 |
| 2.1.0 | `CPF` | MEO | Newest GP set | 3–10 | 3 | 3 | 3 | 3 | 3 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Kuiper-E` | LEO | Operator's set | 0–1 | 6 | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Kuiper-E` | LEO | Operator's set | 2–3 | 12 | 7 | 5 | 3 | 1 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Kuiper-E` | LEO | Newest GP set | 0–1 | 6 | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Kuiper-E` | LEO | Newest GP set | 2–3 | 12 | 3 | 2 | 1 | 1 | 0 | 0 | 0 | 0 |
| 2.1.0 | `OneWeb-E` | LEO | Operator's set | 0–1 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `OneWeb-E` | LEO | Operator's set | 2–3 | 12 | 9 | 8 | 5 | 2 | 0 | 0 | 0 | 0 |
| 2.1.0 | `OneWeb-E` | LEO | Newest GP set | 0–1 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `OneWeb-E` | LEO | Newest GP set | 2–3 | 11 | 8 | 7 | 4 | 3 | 1 | 0 | 0 | 0 |
| 2.1.0 | `OneWeb-E` | LEO | Newest GP set | 3–10 | 1 | 0 | 0 | 0 | 1 | 1 | 0 | 0 | 0 |
| 2.1.0 | `Planet-E` | LEO | Operator's set | 0–1 | 6 | 6 | 6 | 6 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Planet-E` | LEO | Operator's set | 1–2 | 2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Planet-E` | LEO | Operator's set | 2–3 | 10 | 4 | 3 | 2 | 2 | 1 | 0 | 0 | 0 |
| 2.1.0 | `Planet-E` | LEO | Newest GP set | 0–1 | 6 | 6 | 6 | 5 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Planet-E` | LEO | Newest GP set | 1–2 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 2.1.0 | `Planet-E` | LEO | Newest GP set | 2–3 | 11 | 3 | 3 | 2 | 2 | 1 | 0 | 0 | 0 |
| 3.0.0 | `AST-E` | LEO | Operator's set | 0–1 | 6 | 4 | 2 | 0 | 1 | 0 | 0 | 0 | 0 |
| 3.0.0 | `AST-E` | LEO | Operator's set | 2–3 | 12 | 8 | 7 | 6 | 4 | 3 | 0 | 0 | 0 |
| 3.0.0 | `AST-E` | LEO | Newest GP set | 0–1 | 6 | 5 | 4 | 3 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `AST-E` | LEO | Newest GP set | 2–3 | 12 | 7 | 6 | 5 | 4 | 3 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | GEO | Operator's set | 1–2 | 2 | 2 | 2 | 2 | 2 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | GEO | Operator's set | 2–3 | 7 | 7 | 7 | 7 | 3 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | GEO | Operator's set | 3–10 | 3 | 3 | 3 | 3 | 3 | 3 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | GEO | Newest GP set | 0–1 | 4 | 4 | 4 | 4 | 2 | 2 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | GEO | Newest GP set | 2–3 | 3 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | GEO | Newest GP set | 3–10 | 5 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 |
| 3.0.0 | `CPF` | LEO | Operator's set | 2–3 | 10 | 10 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | LEO | Operator's set | 3–10 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | LEO | Newest GP set | 0–1 | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | LEO | Newest GP set | 1–2 | 8 | 8 | 8 | 7 | 2 | 2 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | LEO | Newest GP set | 3–10 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Operator's set | 1–2 | 5 | 5 | 5 | 5 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Operator's set | 2–3 | 7 | 7 | 5 | 3 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Operator's set | 3–10 | 5 | 5 | 5 | 5 | 5 | 1 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Newest GP set | 0–1 | 3 | 3 | 3 | 3 | 3 | 1 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Newest GP set | 1–2 | 4 | 4 | 4 | 4 | 2 | 1 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Newest GP set | 2–3 | 7 | 7 | 7 | 7 | 3 | 0 | 0 | 0 | 0 |
| 3.0.0 | `CPF` | MEO | Newest GP set | 3–10 | 3 | 3 | 3 | 3 | 3 | 1 | 0 | 0 | 0 |
| 3.0.0 | `Kuiper-E` | LEO | Operator's set | 0–1 | 6 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Kuiper-E` | LEO | Operator's set | 2–3 | 12 | 9 | 9 | 5 | 2 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Kuiper-E` | LEO | Newest GP set | 0–1 | 6 | 6 | 6 | 3 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Kuiper-E` | LEO | Newest GP set | 2–3 | 12 | 9 | 6 | 4 | 2 | 0 | 0 | 0 | 0 |
| 3.0.0 | `OneWeb-E` | LEO | Operator's set | 0–1 | 5 | 5 | 3 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `OneWeb-E` | LEO | Operator's set | 2–3 | 12 | 10 | 10 | 10 | 9 | 1 | 0 | 0 | 0 |
| 3.0.0 | `OneWeb-E` | LEO | Newest GP set | 0–1 | 5 | 5 | 5 | 4 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `OneWeb-E` | LEO | Newest GP set | 2–3 | 11 | 9 | 9 | 9 | 9 | 1 | 0 | 0 | 0 |
| 3.0.0 | `OneWeb-E` | LEO | Newest GP set | 3–10 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Planet-E` | LEO | Operator's set | 0–1 | 6 | 6 | 4 | 0 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Planet-E` | LEO | Operator's set | 1–2 | 2 | 2 | 2 | 1 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Planet-E` | LEO | Operator's set | 2–3 | 10 | 9 | 9 | 9 | 5 | 1 | 0 | 0 | 0 |
| 3.0.0 | `Planet-E` | LEO | Newest GP set | 0–1 | 6 | 6 | 6 | 2 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Planet-E` | LEO | Newest GP set | 1–2 | 1 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 |
| 3.0.0 | `Planet-E` | LEO | Newest GP set | 2–3 | 11 | 8 | 8 | 8 | 4 | 1 | 0 | 0 | 0 |
<!-- /measured:time_shifts -->

With method 2.1.0:

- **Under a day old, the method works as D-46 found.** In low orbits every good track
  passed against Kuiper's, OneWeb's and Planet's operator's sets, and none a second late
  did; the newest GP sets of that age did the same. Four of AST SpaceMobile's six passed,
  and two a second late, after a manoeuvre.
- **Two to three days old, 5 km rejects good tracks.** In low orbits, of the satellites
  that manoeuvre, 23 of 46 good tracks passed against the operator's sets and 17 of 46
  against the GP sets; and 9 and 8 of 46 a second late passed, since the set's own error
  along the track and the shift can cancel. The laser-ranging predictions still passed
  all 12 good tracks in low orbits, and none a second late.
- **In medium and geosynchronous orbits a second's shift passes**: such a satellite moves
  a few kilometres a second or less, inside 5 km. Two seconds mostly fail.
- **Shifts of five seconds or more never passed**, against any set.

With method 3.0.0:

- **Under a day old, half a second is caught against operators' sets.** Every good
  track of Kuiper, OneWeb and Planet passed, and none half a second late; against the
  newest GP set, allowed 4 km along the track, 9 of 17 half a second late passed, and
  none a second late.
- **Two to three days old, good tracks pass and a second's shift often does.** A GP set
  that age is allowed 16 km along the track, and so is an operator's set past its day.
  Of the satellites that manoeuvre, 36 of 46 good tracks passed against operators' sets
  and 33 of 46 against GP sets, against 23 and 17 with method 2.1.0; but 20 and 19 a
  second late passed too. That is the price of the term growing with age: the
  follower fetches a request's object every two hours, so the set it verifies with is
  usually hours old.
- **The laser-ranging predictions pass all 10 good tracks in low orbits up to 3 days
  old, and none half a second late.** Past 3 days, the check is inconclusive.
- **Shifts of ten seconds or more never passed.**


## What the numbers suggest

These are candidates for method 3.0.0, decided in step 6.3 (P6-05), not changes.

1. **A GP set's orbit term grows with its age.** In low orbits, the 90th percentile
   suggests about 3 km below a day, about 8 km at one to two days and about 16 km at two
   to three. Past three days a GP set says little about where a satellite is: the median
   was 10.2 km, and a tenth were more than 56 km off. The follower fetches an open
   request's object at most once per two-hour update (step 5.4), so the newest set is
   usually hours old.
2. **In track and across track separately.** The error is nearly all along the
   track in low and medium orbits: up to three days, its 90th percentile across the
   track was below 0.5 km. Not in geosynchronous orbits, where it was 4 to 7 km across
   it too. A term that is larger in track than across it would keep the limit tight
   across the track, where a wrong object in another plane shows, and loose along it,
   where timing and an old set show.
3. **An operator's orbit gets a small term while it is fresh.** SupGP fits its
   operators' data to about 0.1 to 0.4 km, and a set up to a day old was a median 0.1
   to 0.9 km from a later one. The laser-ranging predictions stay that good for days;
   other operators' sets age like GP after a day
   ([How operators' orbits age](#how-operators-orbits-age)).
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
