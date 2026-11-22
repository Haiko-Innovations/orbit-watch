# Visibility

Phase 5, step 5.7 ([#110](https://github.com/Haiko-Innovations/orbit-watch/issues/110)),
decisions [P5-12](decisions.md#p5-12-visibility) and
[D-56](decisions.md#d-56-the-suns-place-from-a-short-formula). Code:
[`sun.py`](../core/src/orbit_watch/sun.py), measured by
[`sun_check.py`](../core/src/orbit_watch/sun_check.py).

An optical observer sees a satellite only when the Sun lights it and the observer's sky
is dark. This page is about the Sun. The simulator's use of it (issue
[#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7)) and a station's visible
passes come in the next parts of step 5.7.

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
  60,480 samples with 211 entries into and exits from the shadow, the formula with the
  cylinder disagreed with Skyfield's `is_sunlit` and DE421 once, for at most 10 seconds.

An error of an arcminute in the Sun's direction moves the edge of the Earth's shadow, at
a satellite 7,000 km from the Earth's centre, by about 2 km, a fraction of a second of its
flight. It moves the end of twilight by seconds, or by minutes near midsummer far north,
where the Sun's elevation changes slowly. Neither changes which passes a station can see.
