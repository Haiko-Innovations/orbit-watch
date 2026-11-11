# Data sources, libraries and standards

Checked on 2026-11-11. Do not copy versions or URLs from here into new code
without checking the current official source again.

## Orbit data: CelesTrak GP

- Query URL: `https://celestrak.org/NORAD/elements/gp.php?{CATNR|INTDES|GROUP|NAME}=value&FORMAT=JSON`
  ([documentation](https://celestrak.org/NORAD/documentation/gp-data-formats.php)).
  `FORMAT` defaults to CSV. CelesTrak recommends the OMM formats; Orbit Watch
  reads OMM JSON and CSV. TLE output cannot hold catalogue numbers above 99999,
  and five-digit numbers ran out in 2026.
- [Usage policy](https://celestrak.org/usage-policy.php): GP data is updated
  once every two hours. Download only what you need, once per update. Since
  2026-03-26 a repeated download of unchanged data gets HTTP 403. More than 50
  HTTP errors (301, 403, 404) in two hours puts the address in the firewall.
  Automated clients must stop at the first non-200 response.
- `orbit-watch fetch-gp` follows this: one request per call, no retries, no
  redirects needed (it uses the canonical HTTPS URL), and no second download of
  the same file within two hours unless `--force` is given.
- Historical GP data is available only through a
  [request form](https://celestrak.org/NORAD/archives/request.php) (CAPTCHA,
  delivered by email, 10 requests per day).
- The data comes from the US Space Force. CelesTrak's pages state no licence or
  redistribution terms. **Orbit Watch does not commit real GP data to this
  repository**; users download it themselves. Whether real element sets may be
  shipped as test fixtures is an open question.

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
