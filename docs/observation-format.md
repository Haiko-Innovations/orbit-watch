# Observation format

Orbit Watch uses one lightweight JSON format of its own and converts to and from
two formats that observers already use: **IOD** and a limited subset of
**CCSDS TDM**.

- JSON Schema: [`core/src/orbit_watch/schemas/observation-set-1.0.schema.json`](../core/src/orbit_watch/schemas/observation-set-1.0.schema.json)
- Examples: [`examples/formats/`](../examples/formats) (all **simulated**, illustrative values)
- Converter: `orbit-watch convert INPUT -o OUTPUT [--sites SITES.json]`

## The JSON observation set (format version 1.0)

One document holds positional (angles-only) optical observations of **one
target** from **one station**.

| Field | Required | Meaning |
|---|---|---|
| `format` | yes | Always `"orbit-watch/observation-set"`. |
| `format_version` | yes | `"1.0"`. A new major version means an incompatible change. |
| `simulated` | yes | `true` when the observations come from a simulator. Required so that simulated data can never be mistaken for real data. |
| `station` | yes | `id`, `latitude_deg`, `longitude_deg` (east positive), `altitude_m` (WGS 84 ellipsoid); optional `name`, `iod_station_number`. |
| `target` | yes | `norad_id` (catalogue number, integer); optional `cospar_id` (`YYYY-NNNA`), `name`. |
| `observations` | yes | List of observations (below). |
| `source` | no | Provenance: `software`, `converted_from` (`iod` or `ccsds-tdm`), `original_designator`, `notes`. |

Each observation:

| Field | Required | Meaning |
|---|---|---|
| `time` | yes | UTC, `YYYY-MM-DDThh:mm:ss[.ffffff]Z`. |
| `time_uncertainty_s` | yes | One-sigma timing uncertainty in seconds. |
| `angle_type` | yes | `"radec"` or `"azel"`. |
| `frame` | for `radec` | `"ICRF"` (J2000 mean equator and equinox) or `"of-date"` (true equator and equinox of the observation date). |
| `ra_deg`, `dec_deg` | for `radec` | Topocentric right ascension and declination in degrees. |
| `az_deg`, `el_deg` | for `azel` | Azimuth (from north through east) and elevation in degrees. |
| `angle_uncertainty_arcsec` | yes | One-sigma uncertainty of each angle component, in arcseconds on the sky. |
| `magnitude` | no | Visual magnitude. |

### Assumptions in version 1.0

These are deliberate simplifications. Each one is a possible future improvement.

- Uncertainties are one-sigma values. IOD does not define what its uncertainty
  fields mean statistically; Orbit Watch reads them as one sigma.
- `ICRF` and J2000/EME2000 are treated as the same frame. They differ by tens
  of milliarcseconds, far below the precision of optical satellite observations.
- Azimuth and elevation are geometric: no atmospheric refraction is modelled.
- Annual aberration and light travel time are not modelled. Together they can
  reach roughly 20 arcseconds, so residual thresholds are kept well above that.
- Leap seconds (`23:59:60`) cannot be represented.

## IOD

The 80-column IOD format is described at
[satobs.org/position/IODformat.html](http://www.satobs.org/position/IODformat.html).
Orbit Watch reads angle formats 1–7 and equinox codes 0 (of date) and 5 (2000).
Other equinoxes (1855, 1875, 1900, 1950, 2050) are rejected with an explanation.

| IOD columns | JSON field |
|---|---|
| 1–5 object number (digits or Alpha-5) | `target.norad_id` |
| 7–15 international designator | `source.original_designator` |
| 17–20 station number | looked up in a sites file (`--sites`) to get `station` |
| 22 station status | lines with `C` or `O` carry no observation and are skipped |
| 24–40 date and time | `time` |
| 42–43 time uncertainty `MX` = M × 10^(X−8) s | `time_uncertainty_s` |
| 45 angle format, 46 equinox | `angle_type`, `frame` |
| 48–61 angles | `ra_deg`/`dec_deg` or `az_deg`/`el_deg` |
| 63–64 position uncertainty `MX` | `angle_uncertainty_arcsec` (unit depends on the angle format) |
| 67–70 magnitude | `magnitude` |

IOD lines carry only a station number, so converting IOD needs a **sites file**
with the station coordinates (see [`examples/formats/sites.json`](../examples/formats/sites.json)).

The reader is lenient with real-world files: non-breaking spaces from web
archives become spaces, blank digits count as non-significant zeros, and a
line whose columns are shifted (for example a short designator) is re-aligned
with a warning. Lines that cannot be parsed are skipped and listed with the reason.

Writing IOD uses angle format 2 (RA/Dec, J2000) or 5 (Az/El). IOD has no field
for "simulated", so the writer adds the comment line
`# orbit-watch: simulated=true`, which the reader recognises.

## CCSDS TDM (limited subset)

Reference: CCSDS 503.0-B-2 *Tracking Data Message*, June 2020, including
Technical Corrigendum 1 (October 2021), KVN syntax.

The **Orbit Watch TDM profile**:

- Header: `CCSDS_TDM_VERS` (1.0 or 2.0), `CREATION_DATE`, `ORIGINATOR`.
- Metadata per segment: `TIME_SYSTEM = UTC`; `PARTICIPANT_1` = station
  identifier (looked up in the sites file); `PARTICIPANT_2` = catalogue number
  of the observed object; `ANGLE_TYPE = RADEC` (with `REFERENCE_FRAME = EME2000`
  or `ICRF`) or `ANGLE_TYPE = AZEL`.
- Data: `ANGLE_1` and `ANGLE_2` records with the same timetag form one
  observation; `MAG` is kept; other data keywords are ignored with a warning.
- `CORRECTION_*` keywords are rejected: send corrected angles.
- Uncertainties and the simulation marker go in metadata comments:

```text
COMMENT orbit-watch angle_uncertainty_arcsec=5
COMMENT orbit-watch time_uncertainty_s=0.01
COMMENT orbit-watch simulated=true
```

If the comments are missing, `--default-angle-uncertainty-arcsec` and
`--default-time-uncertainty-s` supply the values.

## Versioning

The format version is part of every document. Adding optional fields is a
minor change (1.1). Removing or redefining fields is a major change (2.0).
The verification engine states which format versions it accepts.
