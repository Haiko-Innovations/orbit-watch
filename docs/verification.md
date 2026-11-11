# Automated verification

`orbit-watch validate` checks one delivery against a request, a public
reference orbit and a target policy, and explains every result. The method is
**deterministic and versioned**: the same inputs and software versions give a
byte-identical report, so anyone can rerun a verification and get the same
answer.

> This is a prototype. It compares observations with a public reference orbit
> and the request terms. It is **not** production-ready scientific validation
> and does not prove that measurements are physically correct.

Current method: **`orbit-watch-automated-verification` 1.0.0**
(code: [`core/src/orbit_watch/verify/engine.py`](../core/src/orbit_watch/verify/engine.py)).

## Inputs

| Input | Option | Notes |
|---|---|---|
| Delivery | positional | A delivery manifest (`orbit-watch/delivery`, with the SHA-256 of the observation file) or an observation file (JSON, IOD, TDM). |
| Request | `--request` | `orbit-watch/request`: target, window, minimum number of observations, maximum declared uncertainties, accepted angle types. |
| Reference orbits | `--catalog` | GP element sets in OMM form: CelesTrak `FORMAT=JSON` or `FORMAT=CSV`, or the Orbit Watch wrapper used for simulated objects. |
| Target policy | `--policy` | `orbit-watch/target-policy`: the allow-list. Everything not on it is refused. |
| Earlier deliveries | `--previous` (repeatable) | For duplicate and resubmission detection. |
| Sites | `--sites` | Station coordinates, needed for IOD and TDM deliveries. |

The report records the SHA-256 of every input, the method name, version and
parameters, and the versions of orbit-watch, Skyfield, sgp4 and numpy.

## Checks

Checks run in this order. If the file cannot be read, the remaining checks are
skipped. The verdict is `fail` if any check fails, `inconclusive` if none fails
but one could not be decided, and `pass` otherwise.

| Id | Passes when |
|---|---|
| `format` | The file is valid in its format and holds exactly one station and one object. |
| `simulation_label` | Simulated observations are not used for a real request. |
| `target_allowed` | The requested object is on the allow-list. |
| `target_match` | The delivery is for the requested object. |
| `time_window` | Every observation is inside the requested window. |
| `min_observations` | At least the requested number of observations is inside the window. |
| `declared_uncertainty` | Every declared angle and time uncertainty is within the request's limits, and the angle types are accepted. |
| `hash_match` | The file's SHA-256 equals the hash in the delivery manifest (skipped without a manifest). |
| `duplicates` | No timestamp repeats inside the file, the file is not identical to an earlier delivery, and no observation matches one in an earlier delivery (same object, time to 1 ms, both angles to 1″). |
| `orbit_residuals` | Enough observations lie close enough to the reference orbit (below). |

## Orbit residuals

For each observation the engine predicts where the requested object should be,
using SGP4 through Skyfield on the reference element set, as seen from the
station at the observation time. The residual is the angle between the
observed and the predicted direction. It is also split into an **along-track**
component (also given in seconds of time: positive means the object is ahead
of the prediction) and a **cross-track** component.

Each observation gets its own limit:

```
limit = sqrt( (k·σ_angle)² + (k·σ_time·rate)² + θ_ref² )
```

- `σ_angle`, `σ_time`: the declared one-sigma uncertainties;
- `rate`: the apparent angular speed of the object;
- `θ_ref`: the angle subtended by the assumed reference orbit error at the
  observation range, `atan(reference_position_error_km / range)`;
- `k`: the sigma multiplier.

The check passes when at least `min_fraction_within_limit` of the observations
lie within their limits. If the reference epoch is more than
`max_reference_age_days` from any observation, the check is `inconclusive`:
the residuals would mostly measure the age of the orbit.

Parameters of method 1.0.0:

| Parameter | Value | Why |
|---|---|---|
| `reference_position_error_km` | 5.0 | Public GP elements are good to about a kilometre at epoch and degrade quickly; 5 km tolerates elements a few days old. |
| `residual_sigma_multiplier` | 3.0 | Three sigma per observation. |
| `min_fraction_within_limit` | 0.8 | Tolerates a few outliers. |
| `max_reference_age_days` | 7.0 | Skyfield's documentation says elements are generally accurate for a week or two around epoch. |
| `duplicate_time_resolution_s` | 0.001 | Same resolution as IOD times. |
| `duplicate_angle_resolution_arcsec` | 1.0 | Below the precision of amateur optical positions. |

**What this means in practice.** For a low Earth orbit object a few hundred
kilometres away, the reference orbit error alone allows tens of arcminutes. The
residual check therefore catches **wrong objects, wrong times and gross
errors** (degrees, or seconds along the track). It cannot certify
arcsecond-level accuracy, because the public reference orbit is not that good.
The [station quality meter](quality-meter.md) looks at systematic errors in
more detail.

## Known limitations (method 1.0.0)

- Light travel time and annual aberration are not modelled (together up to
  about 20″, far below the residual limits).
- Atmospheric refraction is not modelled for azimuth/elevation data.
- Only the newest element set per object in the catalogue is used.
- One reference orbit source per run; no orbit determination of our own.
- The allow-list is a plain list of catalogue numbers. `orbit-watch allowlist
  build` builds it from civilian groups of the public catalogue (see the
  [README](../README.md#allow-list-civilian-objects-only)).

## Versioning

Any change to a check, a parameter or the report content is a new method
version. Patch: wording only. Minor: new checks or report fields. Major:
changed pass/fail logic or parameters. The committed demo output in
[`examples/simulated/`](../examples/simulated) is regenerated and compared byte
for byte in CI, so an unintended change cannot slip through.
