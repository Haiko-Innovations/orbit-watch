# Automated verification

`orbit-watch validate` checks one delivery against a request, a public
reference orbit and a target policy, and explains every result. The method is
**deterministic and versioned**: the same inputs and software versions give a
byte-identical report, so anyone can rerun a verification and get the same
answer.

> This is a prototype. It compares observations with a public reference orbit
> and the request terms. It is **not** production-ready scientific validation
> and does not prove that measurements are physically correct.

Current method: **`orbit-watch-automated-verification` 3.0.0**
(code: [`core/src/orbit_watch/verify/engine.py`](../core/src/orbit_watch/verify/engine.py)).

| Version | Release | Change |
|---|---|---|
| 3.0.0 | 0.7.0 | The limit is an ellipse along the object's apparent motion and across it. Its orbit term is by the reference orbit's kind (an operator's orbit, a laser-ranging prediction or a GP set), orbit class and age, separately radially, along the track and across it, from step 6.1's measurements; past a row's last age the check is inconclusive ([D-68](decisions.md#d-68-method-300)). It replaces 2.1.0's 5 km and 7 days. Report format 1.2. A request's terms name its method, and its deliveries are verified with it: new requests name 3.0.0, and the engine runs 2.1.0 for those made before ([D-69](decisions.md#d-69-new-requests-use-method-300)). |
| 2.1.0 | 0.6.0 | The element set nearest the observations, when the catalogue holds several sets of the object ([P5-04](decisions.md#p5-04-the-element-set-nearest-the-observations)); the report names it. With one set per object every verdict stays the same. Report format 1.1. |
| 2.0.0 | 0.5.0 | No reference age limit for a SIMULATED catalogue: a residual check that 1.0.0 called inconclusive can now pass or fail. |
| 1.0.0 | 0.1.0 | The first method. |

## Inputs

| Input | Option | Notes |
|---|---|---|
| Delivery | positional | A delivery manifest (`orbit-watch/delivery`, with the SHA-256 of the observation file) or an observation file (JSON, IOD, TDM). |
| Request | `--request` | `orbit-watch/request`: target, window, minimum number of observations, maximum declared uncertainties, accepted angle types. Format 1.1 adds a replay's `replay` block ([D-51](decisions.md#d-51-replays)), which verification does not read. |
| Reference orbits | `--catalog` | GP element sets in OMM form: CelesTrak `FORMAT=csv` or `FORMAT=JSON`, or the Orbit Watch wrapper used for simulated objects and for past sets from SatChecker ([data-sources.md](data-sources.md)). It may hold several sets of one object. |
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
station at the observation time.

**The reference element set.** When the catalogue holds several sets of the
object, the engine takes the set whose epoch is nearest the middle of the
observations, and on a tie the earlier one (since method 2.1.0,
[P5-04](decisions.md#p5-04-the-element-set-nearest-the-observations)). The
report's `reference_orbit` names it:

| Field | Meaning |
|---|---|
| `epoch`, `element_set_no` | The set's epoch and element set number. |
| `element_set_sha256` | SHA-256 of the set's OMM fields as compact canonical JSON (sorted keys, no whitespace), without its `source`. |
| `selection` | `nearest the middle of the observations`, or `the newest in the catalogue` when no observations could be read. |
| `element_sets_in_catalogue` | How many sets of the object the catalogue holds. |
| `source` | Where the set came from, when the catalogue says so: for example SatChecker's endpoint, its `data_source` and `date_collected`, and the SHA-256 of the original set. Never the set itself: reports are published, and real element sets are not ([D-06](decisions.md#d-06-no-real-orbit-data-in-the-repository)). |

Anyone can then fetch the same set and repeat the verification. The residual is the angle between the
observed and the predicted direction. It is also split into an **along-track**
component (also given in seconds of time: positive means the object is ahead
of the prediction) and a **cross-track** component.

Each observation gets its own limit, an ellipse on the sky with axes along the
object's apparent motion (`a`) and across it (`c`):

```
Σ = (k·σ_angle)²·I  +  (k·σ_time·rate)²·a·aᵀ  +  J·diag(E_radial², E_in-track², E_cross-track²)·Jᵀ
within the limit  ⇔  rᵀ·Σ⁻¹·r ≤ 1,    r = (along-track, cross-track residual)
```

- `σ_angle`, `σ_time`: the declared one-sigma uncertainties;
- `rate`: the apparent angular speed of the object;
- `E_…`: the reference orbit's term in kilometres, radially, along its track and
  across it (the table below);
- `J`: how a kilometre in each of those directions shows on the sky from the
  station, along the motion and across it (`geometry.orbit_projection`). It is
  computed by moving the predicted position a kilometre and turning it into angles
  as a prediction is, in the observations' own frame;
- `k`: the sigma multiplier.

When `Σ` is the same in every direction this is method 2.1.0's circle. The report
gives each observation's `along_track_limit_arcsec`, `cross_track_limit_arcsec` and
`normalised_residual` (1 on the ellipse), and names the orbit term it used
(`details.orbit_term`).

**The orbit term** ([`orbit_terms.py`](../core/src/orbit_watch/verify/orbit_terms.py),
[D-68](decisions.md#d-68-method-300)). Each value is the 90th percentile that step 6.1
measured for sets like it ([reference-orbit-accuracy.md](reference-orbit-accuracy.md)),
rounded up: to the next kilometre along the track and the next half kilometre radially
and across it. A set's age is its epoch's largest distance from an observation.

| Kind | Orbit | Age (days) | Radial (km) | In track (km) | Cross track (km) |
|---|---|---|---|---|---|
| An operator's orbit via CelesTrak SupGP | LEO | 0–1 | 0.5 | 2 | 0.5 |
| A laser-ranging prediction via CelesTrak SupGP (`CPF`) | LEO | 0–3 | 0.5 | 2 | 0.5 |
| | MEO | 0–3 | 0.5 | 1 | 0.5 |
| | GEO | 0–3 | 1.5 | 3 | 1.5 |
| A GP set | LEO | 0–1 | 0.5 | 4 | 0.5 |
| | | 1–2 | 0.5 | 9 | 0.5 |
| | | 2–3 | 0.5 | 16 | 0.5 |
| | MEO | 0–3 | 1 | 5 | 0.5 |
| | | 3–7 | 1.5 | 7 | 0.5 |
| | GEO | 0–1 | 2 | 4 | 4.5 |
| | | 1–2 | 2 | 5 | 5.5 |
| | | 2–3 | 2.5 | 8 | 7 |
| | | 3–5 | 3 | 12 | 8.5 |
| Not measured: method 2.1.0's values | HEO | 0–7 | 5 | 5 | 5 |

An operator's orbit past its ages is taken as a GP set of its age: two to three days
old, those of satellites that manoeuvre aged like GP
([D-61](decisions.md#d-61-how-operators-orbits-age)). Past the last age of every kind
that applies, the check is `inconclusive`: the residuals would mostly measure the age
of the orbit. A SIMULATED catalogue has no such limit: the simulator computes
observations from the same elements, so their age does not matter. Past the last age it
keeps the last row's values, and the check's reason says so. In method 1.0.0 the limit
applied to it too, and every delivery on the public testnet more than seven days after
the bundled catalogue's epoch was inconclusive.

The check passes when at least `min_fraction_within_limit` of the observations lie
within their limits. Method 3.0.0's other parameters:

| Parameter | Value | Why |
|---|---|---|
| `residual_sigma_multiplier` | 3.0 | Three sigma per observation. |
| `min_fraction_within_limit` | 0.8 | Tolerates a few outliers. |
| `duplicate_time_resolution_s` | 0.001 | Same resolution as IOD times. |
| `duplicate_angle_resolution_arcsec` | 1.0 | Below the precision of amateur optical positions. |

### Method 2.1.0

The engine still runs it, for the requests made before 2026-11-27, whose terms name it
([D-69](decisions.md#d-69-new-requests-use-method-300); `orbit-watch validate --method
2.1.0`). Its limit is one circle:

```
limit = sqrt( (k·σ_angle)² + (k·σ_time·rate)² + θ_ref² ),    θ_ref = atan(reference_position_error_km / range)
```

and its residual check is inconclusive past `max_reference_age_days` from any
observation. Parameters of method 2.1.0, the same as in 1.0.0:

| Parameter | Value | Why |
|---|---|---|
| `reference_position_error_km` | 5.0 | Public GP elements are good to about a kilometre at epoch and degrade quickly; 5 km tolerates elements a few days old. |
| `residual_sigma_multiplier` | 3.0 | Three sigma per observation. |
| `min_fraction_within_limit` | 0.8 | Tolerates a few outliers. |
| `max_reference_age_days` | 7.0 | Skyfield's documentation says elements are generally accurate for a week or two around epoch. Not applied to a SIMULATED catalogue. |
| `duplicate_time_resolution_s` | 0.001 | Same resolution as IOD times. |
| `duplicate_angle_resolution_arcsec` | 1.0 | Below the precision of amateur optical positions. |

**What this means in practice.** For a low Earth orbit object a few hundred
kilometres away, the reference orbit's error along the track still allows tens of
arcminutes, but across it only a few. The residual check therefore catches **wrong
objects, wrong times and gross errors** (degrees, half a second along the track with a
fresh set, or a few arcminutes across it), and with method 3.0.0 a station placed a
kilometre wrong in some low-orbit tracks
([real-data-validation.md](real-data-validation.md)). It cannot certify
arcsecond-level accuracy, because the public reference orbit is not that good.
The [station quality meter](quality-meter.md) looks at systematic errors in
more detail.

## Known limitations (method 3.0.0)

- Light travel time and annual aberration are not modelled (together up to
  about 20″, below the residual limits).
- Atmospheric refraction is not modelled for azimuth/elevation data.
- The reference is one element set, the one nearest the middle of the
  observations; sets are not combined, and the choice is only among the sets in
  the catalogue given.
- One reference orbit source per run; no orbit determination of our own.
- The orbit term's values come from step 6.1: a few objects of each source and orbit
  class over three runs, and their 90th percentiles. A set from before a manoeuvre is
  wrong whatever its age. Highly elliptical orbits were not measured and keep 2.1.0's
  5 km.
- The station's place has no term of its own. A place rounded to about a kilometre is
  verified as rounded ([P5-11](decisions.md#p5-11-the-stations-place-the-observer-chooses)),
  which can fail a good low-orbit track across the track.
- The allow-list is a plain list of catalogue numbers. `orbit-watch allowlist
  build` builds it from civilian groups of the public catalogue (see the
  [README](../README.md#allow-list-civilian-objects-only)).

## Versioning

Any change to a check, a parameter or the report content is a new method
version. Patch: wording only. Minor: new checks or report fields. Major:
changed pass/fail logic or parameters. The committed demo output in
[`examples/simulated/`](../examples/simulated) is regenerated and compared byte
for byte in CI, so an unintended change cannot slip through.

A request's terms name the method its deliveries are verified with, and the engine
keeps running every method that open or settled requests name, so a report is never
made again with another method. Method 2.1.0's reports stay byte for byte what they
were: a test verifies a committed 2.1.0 report again, and another settles a request
whose stored terms name 2.1.0 and finds its report unchanged after the service is opened
again. The service also waits for, and picks, a reference orbit by the age limit of the
request's method: a replay is delivered, and a simulated station observes a real object,
only with a set that method uses (D-69).
