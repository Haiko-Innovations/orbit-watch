# Orbit determination

Orbit Watch fits an orbit to observations itself (phase 6, step 6.4,
[P6-06](decisions.md#p6-06-orbit-determination-in-the-core),
[D-70](decisions.md#d-70-orbit-determination-in-the-core)). The fit is a batch least
squares fit of SGP4's mean elements to the angles of one or more observation sets, and
of B\* too when the arc is long enough. It starts from a reference orbit, the **start
set**. Later steps use it: step 6.5 as a reference orbit when it is more precise than
the operator's orbit or the GP set
([P6-07](decisions.md#p6-07-a-fitted-orbit-as-a-reference-and-space-tracks-terms-first)),
and step 6.6 to identify objects.

```
orbit-watch fit-orbit observations/*.json --catalog catalog.json --out fit.json
```

The inputs are observation files in any supported format (`--sites` for IOD and TDM)
and a catalogue to start from. The start set is the catalogue's set whose epoch is
nearest the middle of the observations, as verification picks one
([P5-04](decisions.md#p5-04-the-element-set-nearest-the-observations)). The fitted set
keeps the start set's epoch. `--norad-id` chooses the object when the files have
several.

## The method (orbit-watch-orbit-fit 1.0.0)

The fit moves six elements, and B\* over at least two days:

| Element | |
|---|---|
| `mean_motion_rev_per_day` | SGP4's mean motion |
| `af`, `ag` | the eccentricity vector, `e·cos(ω+Ω)` and `e·sin(ω+Ω)` |
| `chi`, `psi` | the inclination's, `tan(i/2)·sin Ω` and `tan(i/2)·cos Ω` |
| `mean_longitude_rad` | `M + ω + Ω` |
| `bstar` | the drag term, only when the observations span at least two days |

**Equinoctial elements** (D-70, choice a). In a near-circular low orbit, the argument of
perigee and the mean anomaly are nearly undefined apart; their sum is not. With these
elements a circular orbit is fitted like any other.

**B\* over two days** (choice b). Over a shorter arc drag hardly shows, and fitting it
would trade it against the mean motion. Below two days the start set's B\* is kept, and
`method.fitted` says which elements were fitted.

**The start set is a measurement** (choice c). Angles from one place over a short arc
measure the direction well and the range poorly. So, at the start set's epoch and at
the middle of each track, the fit's position is held to the start set's: radially,
along the track and across it. Each direction is weighted by the error that step 6.1
measured for sets of that kind and age. This is
[method 3.0.0's orbit term](verification.md#automated-verification), with its 90th
percentile taken as 1.645 standard deviations. Observations less than 15 minutes apart
are one track. Those times are treated as independent. This weighs the start set a
little more than the correlation of its errors over time would. Times past the term's
last age carry no weight. `result.start_set_terms` lists each time with its term.

**Residuals and weights.** Each observation gives two residuals, along the object's
apparent motion and across it, as in verification. They are weighted by the declared
angle uncertainty, plus the declared time uncertainty times the motion's rate along the
motion. The directions are those of the current orbit and are held fixed while the
derivatives are taken.

**The iteration.** Levenberg–Marquardt with central differences. Each element has a
fixed step of some hundred metres to a few kilometres in position: 10⁻⁴ in each element
and 10⁻⁵ in B\*. The problem is nearly linear at that scale. Smaller steps let rounding
in the predictions into the derivatives. Damping starts at 10⁻³ of the normal matrix's
diagonal and changes by a factor of 10. The fit stops after an accepted step smaller
than 10⁻⁴ of every element's standard deviation, after a step that lowers the cost by
less than 10⁻⁹ of it, when no step lowers the cost, or after 30 iterations.
`result.converged` is false only in the last case, and `orbit-watch fit-orbit` then
exits with 1.

The fit then takes two full Gauss–Newton steps, which `result.iterations` does not
count. Near the minimum, whether a step lowers the cost is decided by rounding. In a
direction the observations hardly measure, such as the perigee of a near-circular
orbit, that rounding would decide where the fit stops. Gauss–Newton steps go to the
linear least squares solution itself, which rounding hardly moves.

**Outliers** (choice d). After the fit, the observation furthest off is dropped and the
fit made again, if it is more than three standard deviations off. This is done one
observation at a time, and at most a tenth of the observations are dropped. Dropping
every observation above the threshold at once would also drop good ones that a far
observation pulled the first fit away from. `per_observation` marks the dropped ones
with `"used": false`.

## The fit's document (format 1.0)

`orbit-watch/orbit-fit`, format 1.0:

- `fit_id`: the SHA-256 of the method's name and version, the start set's SHA-256 and
  the observation sets' SHA-256s (each set as compact canonical JSON, whatever its file
  format). The same inputs give the same name.
- `method`: the name, the version, the parameters and the elements fitted.
- `inputs`: the start set (object, epoch, SHA-256, kind) and each observation set.
- `result`:
  - whether the fit converged, and the observations used and dropped;
  - the RMS residuals along the motion and across it, and normalised (about 1 when the
    declared uncertainties are right);
  - the start set's terms;
  - the position's standard deviation at the last observation, and how far the fit
    moved from the start set there, radially, along the track and across it;
  - the fitted elements' standard deviations and correlations, in the order of
    `covariance.parameters`;
  - the fitted set as an OMM record (`omm`), which reads as any catalogue's.
- `per_observation`: each observation's residuals and whether it was used.

**Repeated byte for byte.** Fixed steps and rules, and rounded output:

| Value | Rounded to |
|---|---|
| Mean motion, eccentricity | 9 decimals |
| Inclination, node, mean anomaly | 7 decimals of a degree |
| Argument of perigee | 5 decimals of a degree |
| B\* | 7 significant digits |
| Standard deviations of the elements | 4 significant digits |
| Correlations | 4 decimals |
| Residuals | 0.01″ |
| Positions | 1 m |

The mean anomaly is computed from the mean longitude and the rounded perigee. So the
object's place on its orbit keeps 7 decimals. Rounding the perigee moves the position
by less than a millimetre in a near-circular orbit, and by a few metres at most in a
highly elliptical one. Correlations are rounded absolutely, because near-zero
covariances carry relative rounding noise.

The last evaluation uses the rounded set, so the document describes the set it gives.

**The same on every machine.** The example was first made on aarch64, and CI on x86
found its perigee and covariance different in the last digits. The changes above make a
test pass: inputs changed by 10⁻¹⁰ degrees, far below any observation's precision, give
the same document with three stations and with one, over one day and over three.
The example in [`examples/orbit-fit/`](../examples/orbit-fit) is made again in CI and
compared byte for byte (`orbit-watch demo --orbit-fit`). In it, three simulated stations
see a simulated object on one night. The fit starts from its set moved 4.3 km along the
track and ends within about 20 metres of the truth.

## Its limits

- **One station's clock.** A fit to one station's tracks takes that station's constant
  clock error into the orbit, along the track: the track is simply a little earlier or
  later on the fitted orbit. Only another station, or an operator's orbit, shows such
  an error. Step 6.4 measures this on simulated networks.
- **Range from one place.** A short arc from one place measures the range poorly. The
  start set's weight keeps the fit near it where the angles say little.
- **SGP4's own model.** The fit gives SGP4 mean elements, as GP sets are. A fit cannot
  be better than SGP4's model of the orbit over the arc.
- **Real objects' elements are not published.** A fit starts from a GP or SupGP set.
  Until Space-Track's user agreement is read
  ([#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114)), Orbit Watch
  publishes no fitted elements of real objects. The document of such a fit says so in
  its `notice`, and the measurements publish only residuals, differences and SHA-256s
  (P6-07).

## Measurements

Step 6.4 measures the fit in two more parts. The first uses simulated networks of
stations, where the true orbit is known. The second uses SCORE's real nights from the
video camera, of ACS 3 and PELICAN 3001: a fit of the earlier nights predicts the next
night, and is compared with the GP set available then. Their results will be on this
page.
