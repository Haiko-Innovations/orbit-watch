# The method measured on real data

Phase 5, step 5.3 ([#106](https://github.com/Haiko-Innovations/orbit-watch/issues/106)),
decisions [P5-07](decisions.md#p5-07-measure-first) and
[D-46](decisions.md#d-46-the-method-measured-on-real-data). Code:
[`validation.py`](../core/src/orbit_watch/validation.py).

> **Real data.** Every track here is a real observation of a real satellite, published
> in SCORE by the observers named in the sets' credits. The faults below are put into
> copies of the tracks in memory and never written to a file.

This page measures the automated verification **as it is**: method 2.1.0, which is
method 2.0.0 with the element set nearest the observations (P5-04). Its checks and
parameters are unchanged:

| Parameter | Value |
|---|---|
| The reference orbit's assumed position error | 5 km |
| Each observation's limit | 3 declared sigmas of angle and of time, and the orbit's error, added in quadrature |
| Share of observations within their limits | at least 80 % |
| Oldest reference orbit | 7 days from the observations |

Nothing here changes the method. What the numbers suggest is listed at the end, and
each change will be proposed as a decision of its own.

## In short

- **The good instruments pass.** All 8 tracks of the video camera and both of the
  eVscopes pass. Their median residuals are 136″ and 139″, against limits of about
  900″ and 1,200″.
- **The limit is loose in low orbits.** The reference orbit's 5 km is nearly all of the
  video camera's limit: 97 % of its square. A clock 0.5 s wrong passes in 33 of the 35
  low-orbit tracks tried, and 1 s fails in all of them.
- **The phones fail, and rightly.** None of the 35 phone tracks passes: their times
  run 1.3 to 1.9 s behind. With that offset taken out, 25 of them pass. One observer's
  two phones show the same offset.
- **Most of DECam's tracks fail, and we do not know why.** Each has two observations,
  probably the two ends of one streak.
- **The age of the reference orbit matters more than the method assumes.** In low
  orbits an element set about 3 days old already rejects good tracks, while the method
  accepts sets up to 7 days old.
- **No wrong object was accepted**, out of 397 tracks delivered for another object.
  **Every track made from the reference orbit itself was accepted**, as expected: no
  automated check can catch it, which is what the challenge period is for.
- **Rounding the station's place to about a kilometre changed no result**, nor did any
  assumed angle uncertainty from 10″ to 120″.

## How it was measured

The tracks are the 18 of [`examples/real/`](../examples/real) and the 38 of the
validation set [`validation/real/`](../validation/real), fetched from SCORE one window
at a time, a second apart:

<!-- measured:data -->
| Set | Tracks | Observations | Stations | Objects |
|---|---|---|---|---|
| `examples/real/` | 18 | 2,223 | 7 | 16 |
| `validation/real/` | 38 | 13,713 | 5 | 33 |
| Both | 56 | 15,936 | 7 | 48 |
<!-- /measured:data -->

- **Each track is verified as a delivery** for a request of its own object over the
  track's time, with `verify()` from the file's bytes, as the service does. The
  request's requirements let every track through (at least one observation, angle
  uncertainty up to 3,600″, time uncertainty up to an hour), so the residual check
  against the reference orbit decides. That is the check being measured.
- **The reference orbit** is the element set nearest the track's middle, from the IAU
  CPS's SatChecker, named in each set's `reference-orbits.json`. The sets are not in
  the repository ([D-06](decisions.md#d-06-no-real-orbit-data-in-the-repository)).
- **Faults are put into copies** of the tracks that pass: their times shifted, their
  station moved, their object changed, or their positions computed from the reference
  orbit itself. Each copy is verified like a delivery.
- **The angle uncertainty is assumed.** SCORE gives none for 55 of the 56 tracks, and
  the converter assumed 60″ for them. The last section measures what that changes.
- "Pass", "fail" and "inconclusive" are the residual check's results. "Median residual"
  is the median, over the tracks, of each track's median distance between the observed
  and the predicted position. "Median limit" is the same for the limits.

## Results by instrument

<!-- measured:by_instrument -->
| Instrument | Tracks | Observations | Pass | Fail | Inconclusive | Median residual | Median limit |
|---|---|---|---|---|---|---|---|
| DECam (Blanco 4 m) | 11 | 22 | 1 | 9 | 1 | 2,089″ | 1,101″ |
| Phone (iPhone 12 Mini) | 26 | 468 | 0 | 26 | 0 | 1.00° | 1,619″ |
| Phone (iPhone 17 Pro) | 9 | 63 | 0 | 9 | 0 | 1.04° | 196″ |
| Video camera (WATEC 902H2) | 8 | 15,379 | 8 | 0 | 0 | 136″ | 899″ |
| eVscope | 2 | 4 | 2 | 0 | 0 | 139″ | 1,229″ |
<!-- /measured:by_instrument -->

The video camera's angles are good to about 10″ ([its quality
report](../examples/real/quality/SCORE-a25cc06b7fd1.txt)). Its residuals of about 140″
are therefore mostly the reference orbit's error: about a kilometre at a range of
about 1,200 km.

The one inconclusive track is DECam's SATCOM 3 DEB of 2024-01-19: SatChecker's nearest
element set is more than 7 days from it.

As deliveries, the eVscopes' two tracks fail all the same. Each is one observation that
SCORE holds twice, with the same time and position and two magnitudes, and the method's
check for duplicates refuses that. Every other track's verdict is its residual check's.

## Results by orbit

<!-- measured:by_orbit -->
| Orbit | Tracks | Observations | Pass | Fail | Inconclusive | Median residual | Median limit |
|---|---|---|---|---|---|---|---|
| GEO | 6 | 12 | 1 | 5 | 0 | 2,168″ | 1,141″ |
| HEO | 9 | 25 | 0 | 8 | 1 | 3,202″ | 291″ |
| LEO | 40 | 15,892 | 10 | 30 | 0 | 2,458″ | 1,461″ |
| MEO | 1 | 7 | 0 | 1 | 0 | 1.87° | 185″ |
<!-- /measured:by_orbit -->

The orbit comes from the element set: HEO when the eccentricity is 0.25 or more, LEO
from 11.25 revolutions a day, GEO from 0.9 to 1.1. Orbit and instrument go together
here: the low orbits are the video camera's, the eVscopes' and the phones'; the high
ones are mostly DECam's. So this table says little that the one above does not.

## The limit and its terms

Each observation's limit adds three terms in quadrature: three times its angle
uncertainty, three times its time uncertainty times the object's rate across the sky,
and the angle that the reference orbit's 5 km makes at the object's range. The table
gives the medians.

<!-- measured:limit_terms -->
| Instrument | Angle term 3σ | Timing term 3τ × rate | Orbit term (5 km) | Range | Orbit term's share of the limit² |
|---|---|---|---|---|---|
| DECam (Blanco 4 m) | 180″ | 1,122″ | 28″ | 37,232 km | 0% |
| Phone (iPhone 12 Mini) | 180″ | 614″ | 1,477″ | 698 km | 84% |
| Phone (iPhone 17 Pro) | 180″ | 16″ | 76″ | 13,637 km | 15% |
| Video camera (WATEC 902H2) | 180″ | 4″ | 887″ | 1,164 km | 97% |
| eVscope | 180″ | 487″ | 1,113″ | 955 km | 82% |
<!-- /measured:limit_terms -->

- **In low orbits the orbit term decides.** It makes 82 to 97 % of the limit's square.
  The angle uncertainty, assumed or declared, hardly matters there.
- **DECam's timing term decides.** SCORE gives each DECam observation a time
  uncertainty of half the time between the track's two observations, 5 to 60 s. Against
  a slow object far away, that makes a limit of about 1,100″.
- The iPhone 17 Pro's high orbits make its limit small (196″): far away, 5 km is a small
  angle, and those objects move slowly.

## False rejections

A rejection is false when the track is right: the observer saw the requested object at
the times and from the place they give. For real tracks nobody knows that for certain.
We take the tracks of the instruments that the quality meter finds sound, the video
camera and the eVscopes, as right. **All 10 of them pass** against the nearest element
set. With an older set they do not; see the next section.

The tracks that fail were examined by taking out each one's mean along-track time
offset and verifying again:

<!-- measured:offsets -->
| Instrument | Tracks that fail | Pass with their mean offset taken out | Those offsets |
|---|---|---|---|
| DECam (Blanco 4 m) | 9 | 2 | -212.60 to +183.23 s |
| Phone (iPhone 12 Mini) | 26 | 22 | -1.93 to -1.32 s |
| Phone (iPhone 17 Pro) | 9 | 3 | -1.81 to -1.39 s |
<!-- /measured:offsets -->

- **The phones' rejections are right.** Their angles fit the orbit once the offset is
  taken out, but their times are 1.3 to 1.9 s late, on every low orbit, in September
  and in November. That is a real fault, which the method should catch, and does. Both
  phones belong to one observer. An offset this steady looks like how the times are
  recorded rather than a drifting clock: SCORE asks for the time at the middle of the
  observation, and the time at the end of an exposure of about three seconds would
  give this. Only the observer can say.
- **The iPhone 17 Pro's six other tracks** lie tens to hundreds of seconds, and up to
  2.3°, from the orbit, and five of them are of high orbits. They may be other objects
  than the ones named.
- **DECam's tracks are not understood.** DECam's astrometry is very good. Its residuals
  here lie both along the track (tens to hundreds of seconds) and across it (up to
  1.5°), which neither a time offset nor the reference orbit explains. Two of its
  tracks pass once offsets of minutes are taken out, which says little. This is a
  question for the observers: the follow-up about telling SCORE
  ([#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113)) asks it.

## The reference orbit's age

For each track that passes, the same track was verified against SatChecker's element
sets from about 1, 3, 7 and 14 days before it. Each cell gives the set's age, the
result and the median residual.

<!-- measured:ages -->
| Track | Instrument | Nearest set | About 1 d older | About 3 d older | About 7 d older | About 14 d older |
|---|---|---|---|---|---|---|
| TDRS 9 (2026-01-17) | DECam (Blanco 4 m) | 0.09 d: pass, 517″ | 0.8 d: pass, 517″ | 2.9 d: pass, 517″ | 6.5 d: pass, 517″ | 13.9 d: inconclusive, 517″ |
| PELICAN 3001 (2024-05-08) | Video camera (WATEC 902H2) | 0.34 d: pass, 249″ | 1.1 d: pass, 234″ | 3.4 d: fail, 4.40° | 6.7 d: fail, 2.06° | 13.7 d: inconclusive, 11.13° |
| PELICAN 3001 (2024-05-20) | Video camera (WATEC 902H2) | 0.32 d: pass, 300″ | 1.1 d: pass, 101″ | 2.7 d: pass, 179″ | 6.7 d: fail, 3.98° | 14.4 d: inconclusive, 33.74° |
| PELICAN 3001 (2024-06-05) | Video camera (WATEC 902H2) | 0.58 d: pass, 405″ | 0.7 d: pass, 386″ | 3.1 d: pass, 113″ | 7.1 d: inconclusive, 2.80° | 14.1 d: inconclusive, 22.09° |
| ACS 3 (2024-09-01) | Video camera (WATEC 902H2) | 0.08 d: pass, 30″ | 1.0 d: pass, 336″ | 3.5 d: fail, 8.24° | 7.0 d: fail, 8.24° | 14.2 d: inconclusive, 7.98° |
| CZ-6A R/B (2026-02-01) | eVscope | 0.14 d: pass, 145″ | 1.0 d: pass, 141″ | 3.2 d: pass, 279″ | 6.9 d: pass, 715″ | 14.2 d: inconclusive, 1.50° |
| SPACEMOBILE-006 (2026-02-04) | eVscope | 0.44 d: pass, 134″ | 0.8 d: pass, 265″ | 3.4 d: pass, 534″ | 6.6 d: pass, 1,010″ | – |
| ACS 3 (2024-09-09) | Video camera (WATEC 902H2) | 0.06 d: pass, 191″ | 1.1 d: pass, 140″ | 3.2 d: fail, 2.63° | 7.0 d: fail, 1.83° | 14.4 d: inconclusive, 52.23° |
| ACS 3 (2024-09-13) | Video camera (WATEC 902H2) | 0.01 d: pass, 67″ | 1.1 d: fail, 2.88° | 3.2 d: fail, 1.04° | 7.2 d: inconclusive, 11.00° | 14.0 d: inconclusive, 68.75° |
| ACS 3 (2024-09-21) | Video camera (WATEC 902H2) | 0.23 d: pass, 81″ | 1.3 d: pass, 123″ | 3.1 d: fail, 2,259″ | 7.0 d: fail, 7.32° | 14.0 d: inconclusive, 30.31° |
| ACS 3 (2024-10-05) | Video camera (WATEC 902H2) | 0.09 d: pass, 50″ | 1.1 d: fail, 1.08° | 2.9 d: fail, 8.24° | 7.0 d: fail, 19.59° | 14.3 d: inconclusive, 43.24° |
<!-- /measured:ages -->

- **The nearest set is close.** For these tracks SatChecker had a set within 0.6 days,
  and for all 56 within 0.8 days but one. The method's choice of the nearest set (P5-04)
  is what keeps the good tracks passing.
- **In low orbits a set a few days old is not good enough.** ACS 3, a solar sail, is
  the extreme: its orbit changes so fast that a set one day old can be degrees off.
  PELICAN 3001 fails with sets 3 to 7 days old. So the method's 5 km and 7 days do not
  hold together for low orbits: a good track checked against a 3-day-old set would be
  rejected falsely.
- **High and slow orbits age slowly.** TDRS 9 and the eVscopes' objects pass with sets
  a week old.
- Beyond 7 days the method says inconclusive, as designed; the residuals show why.

## False acceptances: faults put into good tracks

The tracks that pass, and the phone tracks that pass once their offset of 1.3 to 1.9 s
is taken out, were changed in memory and verified again. "Accepted" counts the copies
that pass. Every one of these copies is wrong, so every acceptance is a false one.

**Times shifted**, as a wrong clock, or as an object that many seconds ahead in the same
orbit:

<!-- measured:time_shift -->
| Tracks | n | 0.25 s | 0.5 s | 1 s | 2 s | 5 s | 10 s | 30 s |
|---|---|---|---|---|---|---|---|---|
| DECam (Blanco 4 m), GEO | 1 | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| Phone (iPhone 12 Mini), LEO, offset taken out | 22 | 22 of 22 | 20 of 22 | 0 of 22 | 0 of 22 | 0 of 22 | 0 of 22 | 0 of 22 |
| Phone (iPhone 17 Pro), LEO, offset taken out | 3 | 3 of 3 | 3 of 3 | 0 of 3 | 0 of 3 | 0 of 3 | 0 of 3 | 0 of 3 |
| Video camera (WATEC 902H2), LEO | 8 | 8 of 8 | 8 of 8 | 0 of 8 | 0 of 8 | 0 of 8 | 0 of 8 | 0 of 8 |
| eVscope, LEO | 2 | 2 of 2 | 2 of 2 | 0 of 2 | 0 of 2 | 0 of 2 | 0 of 2 | 0 of 2 |
<!-- /measured:time_shift -->

**The station moved** north:

<!-- measured:station_moved -->
| Tracks | n | 1 km | 10 km | 100 km |
|---|---|---|---|---|
| DECam (Blanco 4 m), GEO | 1 | 1 of 1 | 1 of 1 | 0 of 1 |
| Phone (iPhone 12 Mini), LEO, offset taken out | 22 | 22 of 22 | 0 of 22 | 0 of 22 |
| Phone (iPhone 17 Pro), LEO, offset taken out | 3 | 3 of 3 | 0 of 3 | 0 of 3 |
| Video camera (WATEC 902H2), LEO | 8 | 8 of 8 | 0 of 8 | 0 of 8 |
| eVscope, LEO | 2 | 2 of 2 | 0 of 2 | 0 of 2 |
<!-- /measured:station_moved -->

**Another object, and a track made from the reference orbit.** A track is delivered for
each other object whose element sets reach the track's time, which in this data means
the other objects of the same night. The video camera observed one object a night, so
it has none. A made track has the reference orbit's positions at the track's times, with
10″ of noise:

<!-- measured:wrong_object -->
| Tracks | n | Delivered for another object | Accepted | Inconclusive | Made from the reference orbit: accepted |
|---|---|---|---|---|---|
| DECam (Blanco 4 m), GEO | 1 | 2 | 0 | 0 | 1 of 1 |
| Phone (iPhone 12 Mini), LEO, offset taken out | 22 | 330 | 0 | 1 | 22 of 22 |
| Phone (iPhone 17 Pro), LEO, offset taken out | 3 | 63 | 0 | 0 | 3 of 3 |
| Video camera (WATEC 902H2), LEO | 8 | 0 | 0 | 0 | 8 of 8 |
| eVscope, LEO | 2 | 2 | 0 | 0 | 2 of 2 |
<!-- /measured:wrong_object -->

- **In low orbits a time error of half a second passes, and one second does not.** An
  object half a second ahead in the same orbit, 4 km away, would pass as the requested
  one. The orbit term's 5 km is that wide.
- **In high orbits much larger errors pass.** DECam's TDRS 9 passes with its times 30 s
  wrong and its station 10 km away, because SCORE gives its times an uncertainty of 25 s.
  A request can ask for less: its `max_time_uncertainty_s` refuses such a delivery
  before any residual is computed.
- **Another object fails** in all 397 tries, most of them Starlinks seen the same night,
  but one that is inconclusive: the other object's element set is 7 days from the
  track.
- **A made track always passes.** It fits the reference orbit by construction. Only
  the challenge period and the reviewers can catch it
  ([optimistic-verification.md](optimistic-verification.md)).

## Rounding the station's place

The service keeps a station's place to two decimals of a degree, about a kilometre,
unless the observer chooses the exact place (decision
[P5-11](decisions.md#p5-11-the-stations-place-the-observer-chooses)). Every track was verified again with
its station rounded so:

<!-- measured:rounding -->
| Instrument | Tracks | Results changed | Median change of the median residual | Largest change |
|---|---|---|---|---|
| DECam (Blanco 4 m) | 11 | 0 | 1″ | 5″ |
| Phone (iPhone 12 Mini) | 26 | 0 | 54″ | 137″ |
| Phone (iPhone 17 Pro) | 9 | 0 | 4″ | 76″ |
| Video camera (WATEC 902H2) | 8 | 0 | 72″ | 151″ |
| eVscope | 2 | 0 | 27″ | 27″ |
<!-- /measured:rounding -->

**Rounding changes no result today.** It moves a low orbit's residuals by up to about
150″, fifteen times the video camera's precision, but well within the orbit term's
900″. It would start to matter if that term became much smaller.

## The assumed angle uncertainty

Every track was verified again with each of its angle uncertainties set to 10″, 30″,
60″ and 120″:

<!-- measured:assumed_angle -->
| Instrument | Angle uncertainty in the files | Tracks | Pass with 10″ | Pass with 30″ | Pass with 60″ | Pass with 120″ |
|---|---|---|---|---|---|---|
| DECam (Blanco 4 m) | assumed | 11 | 1 | 1 | 1 | 1 |
| Phone (iPhone 12 Mini) | assumed | 26 | 0 | 0 | 0 | 0 |
| Phone (iPhone 17 Pro) | assumed | 9 | 0 | 0 | 0 | 0 |
| Video camera (WATEC 902H2) | assumed | 7 | 7 | 7 | 7 | 7 |
| Video camera (WATEC 902H2) | declared | 1 | 1 | 1 | 1 | 1 |
| eVscope | assumed | 2 | 2 | 2 | 2 | 2 |
<!-- /measured:assumed_angle -->

**The 60″ assumption changes nothing**: no track's result depends on it. The one track
with its observer's own uncertainties, ACS 3 on 2024-09-21 (a median of 35″), passes
with each value too.

## What the numbers suggest

These are candidates, not changes. Each needs a decision of its own, with these
numbers behind it (P5-07).

1. **The reference orbit's age in low orbits.** A 7-day limit and a fixed 5 km do not
   hold together for low orbits. The limit could depend on the orbit, or the orbit
   term could grow with the set's age. In the service the follower fetches an open
   request's object as it goes (step 5.4), so the nearest set will usually be hours old.
2. **The orbit term in low orbits.** With 5 km, a timing error of half a second, or an
   object 4 km ahead in the same orbit, passes. A smaller term would catch more and
   reject more good tracks against older sets. The two go together with candidate 1.
3. **Time uncertainties in high orbits.** A delivery that declares a time uncertainty
   of 25 s is judged loosely. Requests can already limit it; the request form could
   suggest a value.
4. **Rounding** costs nothing at today's limits. If candidate 2 makes the orbit term
   much smaller than about 150″, the exact place would matter for low orbits.
5. **The phones' 1.6 s.** If the observer confirms a timestamp convention, it belongs
   in the station's profile or the format, not in the method.

## Known answers for reviewer calibration

Real tracks whose correct answer is settled join the reviewers' calibration tasks
([reviewer-accuracy.md](reviewer-accuracy.md#real-known-answer-tasks)).
[`known-answers.json`](../validation/real/known-answers.json) holds 39:
- **approve**: the 8 tracks of the video camera, whose deliveries pass;
- **reject**: 25 phone tracks whose times are off by 1.3 to 1.9 s, and 6 whose
  positions lie a degree or more from the requested object's orbit.

DECam's tracks are left out, since nobody knows yet why they fail, and so are the
eVscopes', whose deliveries fail as duplicates. The measurement writes the file, by
these rules, from `results.json`.

## Every track

<!-- measured:tracks -->
| Track | Instrument | Object | Orbit | Obs. | Result | Median residual | Median limit | Mean along-track | RMS cross-track | Set's age |
|---|---|---|---|---|---|---|---|---|---|---|
| [46601-20211216T0110-SCORE-77d01109b5d1](../validation/real/observations/46601-20211216T0110-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | ATLAS 5 CENTAUR DEB | HEO | 2 | fail | 2,523″ | 926″ | +149.63 s | 1,704″ | 0.77 d |
| [45473-20220829T0801-SCORE-77d01109b5d1](../examples/real/observations/45473-20220829T0801-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | ATLAS 5 CENTAUR DEB | HEO | 2 | fail | 892″ | 799″ | +64.19 s | 420″ | 0.26 d |
| [23756-20230124T0048-SCORE-77d01109b5d1](../validation/real/observations/23756-20230124T0048-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | ECHOSTAR 1 PKM | HEO | 2 | fail | 1,269″ | 386″ | -39.62 s | 917″ | 0.64 d |
| [40259-20230211T0036-SCORE-77d01109b5d1](../validation/real/observations/40259-20230211T0036-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | BREEZE-M R/B | GEO | 2 | fail | 2,681″ | 681″ | -212.60 s | 335″ | 0.16 d |
| [41589-20231231T0151-SCORE-77d01109b5d1](../validation/real/observations/41589-20231231T0151-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | EUTE 117W B | GEO | 2 | fail | 3.66° | 2,704″ | +800.18 s | 1.50° | 0.38 d |
| [32987-20240119T0054-SCORE-77d01109b5d1](../validation/real/observations/32987-20240119T0054-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | SATCOM 3 DEB | HEO | 2 | inconclusive | – | – | – | – | – |
| [28935-20240128T0103-SCORE-77d01109b5d1](../examples/real/observations/28935-20240128T0103-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | ECHOSTAR 10 | GEO | 2 | fail | 1,376″ | 1,139″ | -40.26 s | 1,135″ | 0.37 d |
| [27426-20240131T0054-SCORE-77d01109b5d1](../examples/real/observations/27426-20240131T0054-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | DIRECTV 5 (TEMPO 1) | GEO | 2 | fail | 1,655″ | 1,143″ | -28.49 s | 1,585″ | 0.14 d |
| [32255-20241206T0040-SCORE-77d01109b5d1](../validation/real/observations/32255-20241206T0040-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | ARIANE 5 DEB (SYLDA) | HEO | 2 | fail | 2,656″ | 1,065″ | -111.34 s | 2,470″ | 0.16 d |
| [53962-20250911T0008-SCORE-77d01109b5d1](../validation/real/observations/53962-20250911T0008-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | ATLAS 5 CENTAUR R/B | GEO | 2 | fail | 3,454″ | 2,121″ | +183.23 s | 1,925″ | 0.43 d |
| [27389-20260117T0106-SCORE-77d01109b5d1](../examples/real/observations/27389-20260117T0106-SCORE-77d01109b5d1.json) | DECam (Blanco 4 m) | TDRS 9 | GEO | 2 | pass | 517″ | 1,137″ | +17.06 s | 6″ | 0.09 d |
| [69591-20260930T0210-SCORE-3727e074cd22](../examples/real/observations/69591-20260930T0210-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | SPACEMOBILE-010 | LEO | 41 | fail | 2,370″ | 1,284″ | -1.61 s | 105″ | 0.03 d |
| [69568-20260930T0214-SCORE-3727e074cd22](../validation/real/observations/69568-20260930T0214-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-37938 | LEO | 34 | fail | 1.20° | 1,678″ | -1.93 s | 74″ | 0.01 d |
| [48043-20260930T0214-SCORE-3727e074cd22](../examples/real/observations/48043-20260930T0214-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | ONEWEB-0152 | LEO | 3 | fail | 1,533″ | 714″ | -1.65 s | 341″ | 0.01 d |
| [49175-20260930T0218-SCORE-3727e074cd22](../validation/real/observations/49175-20260930T0218-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-3087 | LEO | 27 | fail | 2,309″ | 1,377″ | -1.33 s | 109″ | 0.08 d |
| [55945-20260930T0220-SCORE-3727e074cd22](../validation/real/observations/55945-20260930T0220-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-5925 | LEO | 51 | fail | 2,191″ | 1,442″ | -1.46 s | 84″ | 0.09 d |
| [51773-20260930T0223-SCORE-3727e074cd22](../validation/real/observations/51773-20260930T0223-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-3624 | LEO | 46 | fail | 1,920″ | 1,396″ | -1.44 s | 51″ | 0.06 d |
| [100365-20260930T0226-SCORE-3727e074cd22](../validation/real/observations/100365-20260930T0226-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | CZ-12 R/B | LEO | 5 | fail | 2,099″ | 1,209″ | -1.40 s | 1,198″ | 0.10 d |
| [36086-20260930T0228-SCORE-3727e074cd22](../validation/real/observations/36086-20260930T0228-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | POISK | LEO | 7 | fail | 2,547″ | 1,783″ | -1.32 s | 95″ | 0.04 d |
| [59083-20260930T0230-SCORE-3727e074cd22](../validation/real/observations/59083-20260930T0230-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-31252 | LEO | 4 | fail | 1.16° | 1,306″ | -1.53 s | 2,951″ | 0.07 d |
| [57290-20260930T0232-SCORE-3727e074cd22](../validation/real/observations/57290-20260930T0232-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-30198 | LEO | 4 | fail | 2,223″ | 1,444″ | -1.50 s | 60″ | 0.05 d |
| [54183-20260930T0234-SCORE-3727e074cd22](../validation/real/observations/54183-20260930T0234-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-5239 | LEO | 14 | fail | 1.16° | 2,066″ | -1.53 s | 98″ | 0.06 d |
| [47353-20261112T0127-SCORE-3727e074cd22](../validation/real/observations/47353-20261112T0127-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-2045 | LEO | 43 | fail | 1.03° | 1,719″ | -1.81 s | 95″ | 0.06 d |
| [58193-20261112T0133-SCORE-3727e074cd22](../validation/real/observations/58193-20261112T0133-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-30822 | LEO | 10 | fail | 1.04° | 1,871″ | -2.18 s | 158″ | 0.02 d |
| [62078-20261112T0137-SCORE-3727e074cd22](../validation/real/observations/62078-20261112T0137-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | CZ-2C R/B | LEO | 17 | fail | 1.07° | 1,892″ | -1.52 s | 92″ | 0.06 d |
| [18749-20261112T0140-SCORE-3727e074cd22](../validation/real/observations/18749-20261112T0140-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | SL-14 R/B | LEO | 12 | fail | 1.14° | 1,609″ | -1.84 s | 1,072″ | 0.01 d |
| [53984-20261112T0146-SCORE-3727e074cd22](../validation/real/observations/53984-20261112T0146-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-5142 | LEO | 30 | fail | 1.15° | 2,041″ | -1.61 s | 78″ | 0.03 d |
| [58207-20261112T0148-SCORE-3727e074cd22](../validation/real/observations/58207-20261112T0148-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | STARLINK-30845 | LEO | 15 | fail | 2,791″ | 1,514″ | -1.64 s | 58″ | 0.05 d |
| [43641-20261112T0153-SCORE-3727e074cd22](../validation/real/observations/43641-20261112T0153-SCORE-3727e074cd22.json) | Phone (iPhone 12 Mini) | SAOCOM 1-A | LEO | 25 | fail | 3,232″ | 1,479″ | -1.72 s | 70″ | 0.11 d |
| [14208-20261119T0123-SCORE-f08826b327e0](../examples/real/observations/14208-20261119T0123-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | SL-3 R/B | LEO | 4 | fail | 3,507″ | 1,629″ | -1.53 s | 72″ | 0.06 d |
| [52621-20261119T0131-SCORE-f08826b327e0](../examples/real/observations/52621-20261119T0131-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | STARLINK-3984 | LEO | 3 | fail | 1.19° | 1,895″ | -1.67 s | 24″ | 0.00 d |
| [46265-20261119T0131-SCORE-f08826b327e0](../examples/real/observations/46265-20261119T0131-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | SAOCOM 1-B | LEO | 10 | fail | 1.03° | 1,729″ | -1.62 s | 108″ | 0.10 d |
| [56530-20261119T0138-SCORE-f08826b327e0](../validation/real/observations/56530-20261119T0138-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | STARLINK-6318 | LEO | 3 | fail | 1.23° | 2,071″ | -1.65 s | 51″ | 0.02 d |
| [57115-20261119T0138-SCORE-f08826b327e0](../validation/real/observations/57115-20261119T0138-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | STARLINK-6085 | LEO | 18 | fail | 1.08° | 2,093″ | -1.58 s | 64″ | 0.00 d |
| [53742-20261119T0141-SCORE-f08826b327e0](../validation/real/observations/53742-20261119T0141-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | STARLINK-4637 | LEO | 6 | fail | 1.05° | 1,816″ | -1.54 s | 147″ | 0.02 d |
| [100800-20261119T0150-SCORE-f08826b327e0](../validation/real/observations/100800-20261119T0150-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | CZ-8A R/B | LEO | 16 | fail | 1,539″ | 861″ | -1.67 s | 95″ | 0.08 d |
| [23343-20261119T0155-SCORE-f08826b327e0](../validation/real/observations/23343-20261119T0155-SCORE-f08826b327e0.json) | Phone (iPhone 12 Mini) | SL-16 R/B | LEO | 20 | fail | 3,524″ | 1,555″ | -1.02 s | 118″ | 0.07 d |
| [18374-20261116T0126-SCORE-7da85e3920f6](../examples/real/observations/18374-20261116T0126-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | SL-12 R/B(AUX MOTOR) | HEO | 4 | fail | 1.04° | 193″ | -16.88 s | 1.23° | 0.06 d |
| [19169-20261116T0127-SCORE-7da85e3920f6](../examples/real/observations/19169-20261116T0127-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | SL-12 R/B(AUX MOTOR) | HEO | 4 | fail | 2.26° | 187″ | +305.61 s | 1.25° | 0.11 d |
| [39174-20261116T0127-SCORE-7da85e3920f6](../examples/real/observations/39174-20261116T0127-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | BREEZE-M DEB (TANK) | HEO | 3 | fail | 2.31° | 196″ | +34.38 s | 2.24° | 0.08 d |
| [21429-20261116T0127-SCORE-7da85e3920f6](../validation/real/observations/21429-20261116T0127-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | SL-6 R/B(2) | HEO | 4 | fail | 2.10° | 185″ | -268.09 s | 1.14° | 0.40 d |
| [17844-20261116T0127-SCORE-7da85e3920f6](../validation/real/observations/17844-20261116T0127-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | SL-14 DEB | LEO | 3 | fail | 3,195″ | 841″ | -2.82 s | 1,108″ | 0.00 d |
| [101286-20261116T0127-SCORE-7da85e3920f6](../validation/real/observations/101286-20261116T0127-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | CZ-2C R/B | LEO | 4 | fail | 2,312″ | 1,313″ | -1.68 s | 108″ | 0.04 d |
| [43641-20261116T0128-SCORE-7da85e3920f6](../validation/real/observations/43641-20261116T0128-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | SAOCOM 1-A | LEO | 31 | fail | 2,582″ | 1,324″ | -1.81 s | 173″ | 0.10 d |
| [62078-20261116T0140-SCORE-7da85e3920f6](../validation/real/observations/62078-20261116T0140-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | CZ-2C R/B | LEO | 3 | fail | 2,023″ | 1,356″ | -1.39 s | 111″ | 0.06 d |
| [43056-20261117T0131-SCORE-7da85e3920f6](../validation/real/observations/43056-20261117T0131-SCORE-7da85e3920f6.json) | Phone (iPhone 17 Pro) | GALILEO 20 (2C6) | MEO | 7 | fail | 1.87° | 185″ | -196.06 s | 2,257″ | 0.25 d |
| [58296-20240508T2142-SCORE-a25cc06b7fd1](../examples/real/observations/58296-20240508T2142-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | PELICAN 3001 | LEO | 108 | pass | 249″ | 1,830″ | -0.09 s | 86″ | 0.34 d |
| [58296-20240520T2128-SCORE-a25cc06b7fd1](../examples/real/observations/58296-20240520T2128-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | PELICAN 3001 | LEO | 97 | pass | 300″ | 1,744″ | -0.12 s | 103″ | 0.32 d |
| [58296-20240605T2137-SCORE-a25cc06b7fd1](../examples/real/observations/58296-20240605T2137-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | PELICAN 3001 | LEO | 126 | pass | 405″ | 1,841″ | -0.15 s | 123″ | 0.58 d |
| [59588-20240901T2024-SCORE-a25cc06b7fd1](../examples/real/observations/59588-20240901T2024-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | ACS 3 | LEO | 1808 | pass | 30″ | 796″ | -0.01 s | 25″ | 0.08 d |
| [59588-20240909T1943-SCORE-a25cc06b7fd1](../validation/real/observations/59588-20240909T1943-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | ACS 3 | LEO | 2870 | pass | 191″ | 929″ | -0.15 s | 38″ | 0.06 d |
| [59588-20240913T2012-SCORE-a25cc06b7fd1](../validation/real/observations/59588-20240913T2012-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | ACS 3 | LEO | 2675 | pass | 67″ | 862″ | -0.04 s | 47″ | 0.01 d |
| [59588-20240921T1924-SCORE-a25cc06b7fd1](../validation/real/observations/59588-20240921T1924-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | ACS 3 | LEO | 3577 | pass | 81″ | 869″ | -0.07 s | 27″ | 0.23 d |
| [59588-20241005T2003-SCORE-a25cc06b7fd1](../validation/real/observations/59588-20241005T2003-SCORE-a25cc06b7fd1.json) | Video camera (WATEC 902H2) | ACS 3 | LEO | 4118 | pass | 50″ | 799″ | +0.02 s | 16″ | 0.09 d |
| [66051-20260201T0146-SCORE-ae5a282af528](../examples/real/observations/66051-20260201T0146-SCORE-ae5a282af528.json) | eVscope | CZ-6A R/B | LEO | 2 | pass | 145″ | 1,443″ | -0.06 s | 93″ | 0.14 d |
| [67232-20260204T1027-SCORE-caef8cca1acf](../examples/real/observations/67232-20260204T1027-SCORE-caef8cca1acf.json) | eVscope | SPACEMOBILE-006 | LEO | 2 | pass | 134″ | 1,014″ | +0.10 s | 46″ | 0.44 d |
<!-- /measured:tracks -->

## Reproduce

From the repository's `core` directory:

```sh
orbit-watch fetch-orbits ../examples/real/reference-orbits.json
orbit-watch fetch-orbits ../validation/real/reference-orbits.json
orbit-watch measure-method
```

The first two fetch the element sets into a cache outside the repository, two seconds
apart, and check each one's SHA-256. The last runs the measurement, in about a minute,
and writes [`results.json`](../validation/real/results.json), `known-answers.json` and
this page's tables. `results.json` names the method's version, orbit-watch's version and
the SHA-256 of every observation file and element set. With `--check` it writes
nothing and fails when anything differs, and CI runs it that way.
