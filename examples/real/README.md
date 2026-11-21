# Real observations from SCORE

> **Real data.** These are real observations of real satellites, made and published by
> the observers named in [CREDITS.md](CREDITS.md). Nothing here is SIMULATED.

This example holds 18 tracks of real positional observations from 7 stations and five
kinds of instrument. The observers published them in [SCORE](https://score.cps.iau.org),
the IAU CPS's Satellite Constellation Observation Repository, under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Orbit Watch converted them to
its own format (decision
[P5-06](../../docs/decisions.md#p5-06-real-observations-from-score), step 5.2). The
tracks were chosen to include both good ones and bad ones, and only civilian objects
([D-05](../../docs/decisions.md#d-05-civilian-objects-only-through-an-allow-list)).

| Instrument | Tracks | Objects | What the quality meter finds |
|---|---|---|---|
| Video camera (WATEC 902H2, 85 mm lens), Leiden | 4 | PELICAN 3001, ACS 3 | Angle precision 9.6″, timing 0.017 s; no clock offset |
| DECam on the 4 m Blanco telescope, Cerro Tololo | 4 | TDRS 9, DIRECTV 5, ECHOSTAR 10, an Atlas 5 Centaur part | Two exposures per object, too few for precision; slow objects far away |
| eVscope 1.0 and 2.0 | 2 | SPACEMOBILE-006, a CZ-6A rocket body | Two observations per object, too few for precision |
| Phone (iPhone 12 Mini), September and November | 5 | SPACEMOBILE-010, ONEWEB-0152, SAOCOM 1-B, STARLINK-3984, an SL-3 rocket body | Every object about 1.6 s behind its prediction: the phone's clock |
| Phone (iPhone 17 Pro) | 3 | Two SL-12 motors, a Breeze-M tank | Tens to hundreds of seconds off: wrong times or wrong objects |

The [quality reports](quality) are in `quality/`, one per station, as JSON and as text.

## What the files hold

Each file in [`observations/`](observations) is an Orbit Watch observation set, format
1.1 ([observation-format.md](../../docs/observation-format.md)), one station and one
object:
- the station's place, **as the observer published it in SCORE**. The station's ID is
  derived from the place, the instrument and the observers.
- the observations: time, right ascension and declination in the ICRF, measured by the
  observer against Gaia DR3 stars, and the uncertainties.
- `source.origin`: SCORE, the observers' ORCID iDs, SCORE's ID of each observation, the
  licence and the date they were fetched.

**SCORE gives no angle uncertainty for these observations**, so the converter assumed
60″, one arcminute, for all of them. Each file says so in `source.notes` and in
`source.origin.assumed_angle_uncertainty_arcsec`. The quality meter's "the uncertainty
you declare" means this assumption here, not the observer's statement. Step 5.3 measures
what the assumption changes.

A phone's place jitters by metres between observations. Observations within 100 m of a
station's first place share it, and each file says how far its observations' places
differ.

[`tracks.json`](tracks.json) lists the windows that were fetched. It also names the one
track left out, of 55945. Six of its observations have places 0.1 to 10 km from the
others, and the converter of step 5.2 split the track there. Since step 5.3 the
converter leaves such observations out, and the track is in the validation set
[`validation/real/`](../../validation/real), where step 5.3 measures the method on these
tracks and 38 more.

## Reference orbits

Real element sets are not committed
([D-06](../../docs/decisions.md#d-06-no-real-orbit-data-in-the-repository)).
[`reference-orbits.json`](reference-orbits.json) names the 18 sets, one nearest each
track, from the IAU CPS's SatChecker. One command fetches them into a cache outside the
repository and checks every SHA-256 ([data-sources.md](../../docs/data-sources.md)):

```sh
orbit-watch fetch-orbits examples/real/reference-orbits.json -o catalog.json
orbit-watch score-station examples/real/observations/*-SCORE-a25cc06b7fd1.json --catalog catalog.json
```

## Made with

From the repository's `core` directory, a second or more apart and stopping at the first
problem, for each window in `tracks.json`:

```sh
orbit-watch fetch-score --catnr 58296 --start 2024-05-08T20:30:00Z --end 2024-05-08T22:30:00Z -o raw/58296.json
```

then:

```sh
orbit-watch convert-score raw/*.json --out ../examples/real/observations \
  --assume-angle-uncertainty 60 --credits ../examples/real/CREDITS.md
orbit-watch fetch-satchecker --catnr 58296 --near <the middle of the track> -o set.json \
  --manifest ../examples/real/reference-orbits.json      # for each track
orbit-watch fetch-orbits ../examples/real/reference-orbits.json -o catalog.json
orbit-watch score-station ../examples/real/observations/*-SCORE-<station>.json \
  --catalog catalog.json --report ../examples/real/quality/SCORE-<station>.json \
  > ../examples/real/quality/SCORE-<station>.txt          # for each station
```

The quality reports name the orbit-watch version, so a release regenerates them, as it
does the simulated examples. Fetched on 2026-11-21.

## Personal data

A station's place may be someone's home, and an ORCID iD names a person. The observers
published both in SCORE themselves, under CC BY 4.0. Orbit Watch keeps them as
published, because verification needs the exact place. The
[privacy notice](../../docs/legal/privacy-notice.md#observations-that-others-have-published)
says what we keep and why. An observer can ask for their observations to be removed:
write to info@haikoinnovations.com with "Orbit Watch privacy" in the subject line. They
are then removed from the next version of the repository.

## Credits

See [CREDITS.md](CREDITS.md): the observers of each file, and the statements that SCORE
and SatChecker ask users to show.
