# Visibility

Phase 5, step 5.7 ([#110](https://github.com/Haiko-Innovations/orbit-watch/issues/110)),
decisions [P5-12](decisions.md#p5-12-visibility) and
[D-56](decisions.md#d-56-the-suns-place-from-a-short-formula). Code:
[`sun.py`](../core/src/orbit_watch/sun.py), measured by
[`sun_check.py`](../core/src/orbit_watch/sun_check.py).

An optical observer sees a satellite only when the Sun lights it and the observer's sky
is dark. This page is about the Sun and what follows from it: the simulator observes only
what a station can see (issue
[#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7),
[D-57](decisions.md#d-57-the-simulator-observes-only-what-a-station-can-see)), and a
station sees its visible passes for a request
([D-58](decisions.md#d-58-a-stations-visible-passes-for-a-request)).

## The Sun's place

The core computes the Sun's place from the US Naval Observatory's
[approximate solar coordinates](https://aa.usno.navy.mil/faq/sun_approx), read on
2026-11-22. The page gives them "to an accuracy of about 1 arcminute within two centuries
of 2000":

- `D` is the Julian date in Universal Time minus 2451545.0;
- the mean anomaly `g = 357.529 + 0.98560028 D`, the mean longitude
  `q = 280.459 + 0.98564736 D` and the apparent ecliptic longitude
  `L = q + 1.915 sin g + 0.020 sin 2g`, all in degrees;
- the distance `R = 1.00014 − 0.01671 cos g − 0.00014 cos 2g` in astronomical units;
- the mean obliquity `e = 23.439 − 0.00000036 D`;
- the right ascension `atan2(cos e sin L, cos L)` and the declination `asin(sin e sin L)`.

These refer to the equator and equinox of date. Skyfield's precession and nutation
matrix turns them into the ICRS axes of its geocentric positions, and its Earth rotation
gives a station's zenith. Neither needs a file. JPL's DE421, by comparison, is 17 MB.

- **The Sun's elevation** is the angle between the station's geodetic zenith and the
  Sun's direction, without refraction. The Sun's parallax, under 9″, is left out.
- **A dark sky** has the Sun at least 6° below the horizon, the end of civil twilight.
  This is the default; it is a setting.
- **Sunlight**: a satellite is lit when it is on the Sun's side of the Earth, or outside
  the cylinder of the Earth's shadow, whose radius is the Earth's equatorial radius,
  6378.137 km.

## Measured against JPL's DE421

`orbit-watch measure-sun` measured all three once against DE421 through Skyfield 1.55.
The result is in [`validation/sun/results.json`](../validation/sun/results.json).
DE421 was fetched once into the cache, outside the repository
(`orbit-watch measure-sun --fetch`); no test and no CI job fetches it. With it in the
cache, `core/tests/test_sun.py` repeats the measurement and compares.

| What | Samples | Median | 95 % | Largest |
|---|---|---|---|---|
| The Sun's direction from the Earth's centre, daily, 1900–2049 | 54,788 | 13.0″ | 31.6″ | 55.9″ |
| The same, 2000–2049 | 18,263 | 12.7″ | 30.4″ | 44.4″ |
| The Sun's elevation at SIM-ESPOO (60.2° N), every 10 minutes through 2026 | 52,560 | 12.2″ | 27.3″ | 37.4″ |

- **The formula keeps its promise:** the largest error over DE421's whole span is under
  an arcminute.
- **Twilight:** with the Sun at −6° as the limit, the formula and DE421 disagreed on
  whether the sky at SIM-ESPOO was dark in 3 of 52,560 samples, each within seconds of
  the moment the Sun crossed the limit.
- **Sunlight:** every 10 seconds for a week of SIM-CUBESAT-A's orbit from 2026-11-01,
  60,480 samples with 212 entries into and exits from the shadow, the formula with the
  cylinder disagreed with Skyfield's `is_sunlit` and DE421 7 times, each for at most
  10 seconds, all at the shadow's edge. (Before step 5.7's second part moved the
  SIMULATED orbits to cross the equator in the evening, it was once in 211.)

An error of an arcminute in the Sun's direction moves the edge of the Earth's shadow, at
a satellite 7,000 km from the Earth's centre, by about 2 km, a fraction of a second of its
flight. It moves the end of twilight by seconds, or by minutes near midsummer far north,
where the Sun's elevation changes slowly. Neither changes which passes a station can see.

## Passes, and what the simulator sees

`orbit_watch.passes` finds an object's passes over a station above an elevation limit,
and samples each every 10 seconds for its visible part: lit, under a dark sky. The
simulator centres its observations on the highest point of each visible part and keeps
only those within it. A pass without a visible part gives none.

The SIMULATED objects of the bundled catalogue are sun-synchronous. Until step 5.7 they
crossed the equator northwards at about 22:40 local time. Over Finland in November that
put every pass at about 22:30, in the Earth's shadow, or at about 10:30, in daylight: a
station could never see them. Their ascending node is now 315° further east (right
ascension 330° instead of 15° at the epoch), so they cross the equator at about 19:30.
Their evening passes, at about 15:45 and 17:20 UTC, are then lit under a dark sky.
Nothing else in their orbits changed.

## A station's visible passes

`GET /v1/requests/{id}/passes` lists, for a station, the passes of a request's object over
the station's profile place in the request's window, above its instrument's elevation
limit, and the visible part of each. A request's page shows them to a station as "Your
visible passes", while the request is open, funded or reserved by it. A window longer
than a week is listed for its first seven days.
