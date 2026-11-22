# Data sources, libraries and standards

Checked on 2026-11-11; SatChecker on 2026-11-20, and CelesTrak's usage policy and
groups again on 2026-11-21.
Do not copy versions or URLs from here into new code without checking the
current official source again.

## Orbit data: CelesTrak GP

- Query URL: `https://celestrak.org/NORAD/elements/gp.php?{CATNR|INTDES|GROUP|NAME}=value&FORMAT=csv`
  ([documentation](https://celestrak.org/NORAD/documentation/gp-data-formats.php)).
  CelesTrak recommends the OMM formats; Orbit Watch reads OMM CSV and JSON. TLE
  output cannot hold catalogue numbers above 99999, and five-digit numbers ran
  out on 2026-07-11.
- [Usage policy](https://celestrak.org/usage-policy.php), updated 2026-11-16:
  - GP data is updated once every two hours. Download only what you need, when
    you use it, once per update. A 403 is "usually sent in response to abusive
    behavior", and may come with a message that says how to lift it.
  - Ask for `FORMAT=csv`: "FORMAT=json is ~3 times the size". Ask for
    compressed data (gzip or brotli).
  - Automated clients "should immediately stop querying when it receives any
    non-HTTP 200 responses and report the results to a human". After a 500 or
    a 503, "All requests should stop for at least 15 minutes". A 404 usually
    means an outdated URL, and too many errors put the address in the firewall.
  - Large lists, such as `active` and `starlink`, are limited. On 2026-11-20 a
    download of `GROUP=active` stopped at about 1.2 MB.
  - CelesTrak blocks addresses, not users: many users behind one address are
    blocked together.
- `orbit-watch fetch-gp` follows this
  ([P5-02](decisions.md#p5-02-current-reference-orbits-from-celestrak-one-object-at-a-time)):
  one request per call, CSV with gzip, no retries, no redirects needed (it
  uses the canonical HTTPS URL), and no second download of the same file
  within two hours unless `--force` is given. An answer that is not 200 stops
  it, with what the policy asks next: for example, wait 15 minutes after a
  503, and do not ask again after a 404. Ask for one object or a small group.
- The service's follower follows it too
  ([D-48](decisions.md#d-48-the-follower-fetches-reference-orbits)): one object
  at a time, only the objects of open requests, at most once per update, at
  most three requests per run. At the first answer that is not 200, or no
  answer, it stops asking and the uptime check alerts a person, who resumes it.
- For the allow-list the follower fetches six small groups, each at most once a
  day ([D-49](decisions.md#d-49-real-objects-on-the-allow-list)): `science`,
  `education`, `amateur` and `cubesat` to include, `military` and `radar` to
  exclude. These are the group names in the links of
  [CelesTrak's index of GP data](https://celestrak.org/NORAD/elements/), read on
  2026-11-21. Large groups, such as `active` and `starlink`, are never fetched.
  It keeps the groups' objects and names, not their element sets.
- Historical GP data is available only through a
  [request form](https://celestrak.org/NORAD/archives/request.php) (CAPTCHA,
  delivered by email, 10 requests per day).
- The data comes from the US Space Force. CelesTrak's pages state no licence or
  redistribution terms, and Space-Track's user agreement governs
  redistribution. **Orbit Watch does not commit real GP data to this
  repository** ([D-06](decisions.md#d-06-no-real-orbit-data-in-the-repository),
  [P5-05](decisions.md#p5-05-orbit-data-stays-out-of-the-repository)); users
  download it themselves. Reading Space-Track's agreement is a follow-up
  ([#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114)).

## Past orbit data: SatChecker

The IAU CPS's [SatChecker](https://satchecker.readthedocs.io/en/latest/tools_data_access.html)
(version 1.9.0) keeps the element sets of Space-Track and CelesTrak and gives
the one nearest a given time, without an account
([P5-03](decisions.md#p5-03-past-reference-orbits-from-satchecker)):
- `GET https://satchecker.cps.iau.org/tools/get-nearest-tle/?id=<catalogue number>&id_type=catalog&epoch=<Julian date>`,
  for the past: TLEs "remain the record for historical dates";
- `get-nearest-omm/` with the same parameters, for OMM data, which SatChecker
  keeps going forward.

Its [notes](https://satchecker.readthedocs.io/en/latest/notes.html) say that
"Public Space-Track TLEs for LEO satellites are often off by several
arcminutes", and that TLEs "are only good for a maximum of two weeks".

`orbit-watch fetch-satchecker --catnr N --near TIME -o set.json` asks for the
set nearest a time, in one request with no retries, and writes it as an Orbit
Watch catalogue. A TLE is converted to OMM form with sgp4's exporter, which
gives the same orbit to a few millimetres. The record's `source` names
SatChecker's endpoint, its `data_source` and `date_collected`, and the TLE.

The service's follower asks SatChecker the same way for a request whose window has
ended, such as a replay: the set nearest the middle of the window, once, and only when
no kept set lies within a day of it. It stops at the first answer that is not 200, as it
does for CelesTrak ([D-48](decisions.md#d-48-the-follower-fetches-reference-orbits)).

SatChecker asks for this acknowledgement: "This research made use of data
and/or services provided by the International Astronomical Union Centre for
the Protection of the Dark and Quiet Sky (IAU CPS) SatHub. The development of
SatChecker has been supported by the National Science Foundation (NSF) under
grant numbers: AST 2332735 and AST 2332736. SatChecker is hosted at the NSF
NOIRLab. Any opinions, findings, and conclusions or recommendations expressed
in this material are those of the author(s) and do not necessarily reflect the
views of the NSF, IAU, NSF NOIRLab, SKAO, ESO, or any host or member
institution of the IAU CPS."
([acknowledgements](https://satchecker.readthedocs.io/en/latest/acknowledgements.html))

## Real orbits in examples and tests: manifests and the cache

Examples and tests with real data name their reference orbits instead of
committing them ([P5-05](decisions.md#p5-05-orbit-data-stays-out-of-the-repository)).
A manifest (`orbit-watch/reference-orbits` 1.0) lists, for each element set:
- the catalogue number;
- the kind, `tle` or `omm`;
- the source, `satchecker`;
- the epoch;
- the SHA-256 of the original set: of the TLE's two lines, each ending in a
  newline, or of the OMM fields as compact canonical JSON.

```sh
orbit-watch fetch-satchecker --catnr 59588 --near 2024-09-01T20:00:00Z \
  -o acs3.json --manifest orbits.json                 # name a set in a manifest
orbit-watch fetch-orbits orbits.json -o catalog.json  # fetch what the cache lacks
```

`fetch-orbits` asks SatChecker only for the sets the cache lacks, by their
exact epoch, one request at a time and two seconds apart. It stops at the
first answer that is not 200, and at any set whose SHA-256 is not the
manifest's. The cache is `$ORBIT_WATCH_CACHE`, or `orbit-watch` under
`$XDG_CACHE_HOME` (by default `~/.cache/orbit-watch`), outside the repository.

Tests that need real sets, such as those that
[`core/tests/data/reference-orbits.json`](../core/tests/data/reference-orbits.json)
names, are skipped without the cache. CI keeps the cache in GitHub Actions'
cache only, never in the repository or in an artifact, and asks SatChecker
only when the cache lacks a set.

## Real observations: SCORE

The IAU CPS's [SCORE](https://score.cps.iau.org), the Satellite Constellation
Observation Repository, publishes observers' positional and brightness observations of
satellites ([P5-06](decisions.md#p5-06-real-observations-from-score)). Read on
2026-11-20 and 2026-11-21:
- **Licence.** The [use policy](https://score.cps.iau.org/policy), last updated
  2024-12-02: "Data will be shared under the Creative Commons Attribution (CC-BY) 4.0
  licence", and "If you use data from SCORE, you must follow the CC-BY licences and
  credit the observers appropriately". Any "website or web service that uses SCORE data"
  must show a statement, which [`examples/real/CREDITS.md`](../examples/real/CREDITS.md)
  quotes. The policy also asks users to tell SCORE that they use it: a follow-up
  ([#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113)).
- **Fields** ([data format](https://score.cps.iau.org/data-format)): the time at the
  middle of the observation and its uncertainty; right ascension and declination
  "measured from the observation with respect to Gaia DR3 astrometric catalog stars
  (ICRF)"; their variances `sigma_2_ra` and `sigma_2_dec` in arcsec²; the observer's
  place; the instrument; the observers' ORCID iDs; a `potentially_discrepant` flag.
- **API** ([overview](https://score.cps.iau.org/api-access), OpenAPI at
  `https://score.cps.iau.org/api/openapi.json`, version 2.0.0): "rate-limited to 10
  requests per second". `GET /api/observations/search` takes `satellite_number`,
  `start_date`, `end_date`, `limit` and `offset`, and answers `items` and `count`. The
  full download is behind a CAPTCHA, and is never used.

`orbit-watch fetch-score --catnr N --start T --end T -o raw.json` asks for one
object's observations in one window, in pages of 100, at least a second apart. It stops
at the first answer that is not 200, and after a 429 or a 5xx it says to wait at least
15 minutes. On 2026-11-20, pages of 1,000 observations a second answered 500 and 503.

`orbit-watch convert-score raw/*.json --out DIR --credits CREDITS.md` writes each track
as an observation set, format 1.1 ([observation-format.md](observation-format.md)):
- **A track** is one object, one instrument and one set of observers, with no gap
  longer than 15 minutes.
- **A station** is one instrument and set of observers at one site. Places within 100 m
  of a station's first place share it, since a phone's place jitters by metres.
  The file says how far its observations' places differ.
- **A place that jumps.** A phone's place sometimes jumps by 0.1 to 10 km for one
  observation and comes back. When no other observation of a track lies within 100 m
  of one, while most of them share a place, it is left out: the file says how many and
  how far, and the command counts them. A phone that truly moves keeps every
  observation ([D-46](decisions.md#d-46-the-method-measured-on-real-data)).
- **The angle uncertainty** is the square root of the larger of SCORE's two variances.
  When SCORE gives none, which is common, `--assume-angle-uncertainty` says what to
  assume; each file records it. Without it such observations are left out, and the
  command counts them.
- `source.origin` names SCORE, the observers, SCORE's observation IDs, the licence and
  the date fetched.

Two sets are committed: the example [`examples/real/`](../examples/real), and the
validation set [`validation/real/`](../validation/real), on which step 5.3 measures the
verification method ([real-data-validation.md](real-data-validation.md)).

SCORE also gives SatChecker's predicted position for each observation. Orbit Watch does
not use it: it computes its own from the element set the manifest names.

## The Sun: a formula, measured against JPL's DE421

The Sun's place comes from the US Naval Observatory's
[approximate solar coordinates](https://aa.usno.navy.mil/faq/sun_approx), a formula, not
a data file ([visibility.md](visibility.md),
[D-56](decisions.md#d-56-the-suns-place-from-a-short-formula)). To measure it once,
`orbit-watch measure-sun --fetch` fetches JPL's DE421 (`de421.bsp`, 1900 to 2050, 17 MB)
through Skyfield's loader into the cache, outside the repository. The service, the tests
and CI never fetch it.

## Observation formats

- IOD: [satobs.org/position/IODformat.html](http://www.satobs.org/position/IODformat.html)
  (G. D. Lewis, version 0, 1998, clarified 2002).
- CCSDS TDM: [CCSDS 503.0-B-2](https://ccsds.org/Pubs/503x0b2c1.pdf), Blue Book,
  June 2020, including Technical Corrigendum 1 (October 2021).

## Python libraries

| Library | Version locked | Licence | Used for |
|---|---|---|---|
| [Skyfield](https://rhodesmill.org/skyfield/) | 1.55 | MIT | satellites from OMM (`EarthSatellite.from_omm`), topocentric positions, pass search; built-in leap-second table, no downloads |
| [sgp4](https://pypi.org/project/sgp4/) | 2.27 | MIT | SGP4 propagation (C++ accelerated), used through Skyfield |
| [NumPy](https://numpy.org/) | 2.5.4 | BSD-3-Clause and others | arrays |
| [jsonschema](https://python-jsonschema.readthedocs.io/) | 4.26.0 | MIT | JSON Schema (draft 2020-12) validation |
| [Astropy](https://www.astropy.org/) | not used in phase 0 (8.0.2 is current, BSD-3-Clause) | | candidate for older equinoxes (B1950) and refraction |

Versions are locked in [`core/uv.lock`](../core/uv.lock). uv only resolves
files that have been public for 14 days (`exclude-newer = "14 days"`), the same
rule as the Dependabot cooldown.

## Community

- [SeeSat-L](http://www.satobs.org/seesat/) is the amateur satellite observers'
  mailing list where IOD observations are posted. In October and November 2026
  nearly all IOD posts were about classified objects, which Orbit Watch does
  not handle. In the same weeks the list carried observation requests from
  satellite teams (HYPSO-1, Swift) close to re-entry, which is exactly the use
  case Orbit Watch wants to serve.
