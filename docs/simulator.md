# Station simulator (SIMULATED data)

`orbit-watch simulate` produces positional observations of an object as a
simulated station would report them. Everything it produces is marked as
simulated (`"simulated": true` in JSON, a marker comment in IOD and TDM).

```sh
orbit-watch simulate --target 339001 --profile sim-cmos-gps \
  --start 2026-11-01T00:00:00Z --end 2026-11-02T00:00:00Z --seed 1 -o sim.json
```

## How it works

1. Finds the passes of the object above the profile's elevation limit
   (Skyfield `find_events`, SGP4 on the GP element set), and the part of each
   that the station can see: the object lit by the Sun, the station's sky dark,
   with the Sun at least 6° below the horizon (`orbit_watch.passes`,
   [visibility.md](visibility.md), [D-57](decisions.md#d-57-the-simulator-observes-only-what-a-station-can-see)).
   Passes without a visible part are left out.
2. Places `points_per_pass` observations `cadence_s` apart around the highest
   point of each pass's visible part, and keeps only those that fall within it.
3. For each observation: drops it with `dropout_probability`, adds timing noise
   (`time_noise_s`) and the station clock offset (`clock_offset_s`, positive =
   the station clock runs ahead of UTC), computes the true direction and adds
   angle noise (`angle_noise_arcsec` per axis).
4. Writes the declared uncertainties of the profile, not the true noise.

Randomness comes from `random.Random(seed)` with a Box-Muller transform built
on `random()`, whose sequence Python guarantees across versions: the same
seed gives the same observations.

`simulate(..., dark_sky_deg=-6.0)` is the default; another limit sets a lighter
or darker sky, and `dark_sky_deg=None` observes around every culmination, lit or
not, as the simulator did before step 5.7. The command line's `--dark-sky-deg`
does the same, with `--any-light` for the old way.

Not modelled yet (good first issues): weather, atmospheric refraction,
aberration, light travel time and star-catalogue errors.

## Station profiles

Built-in profiles are in
[`core/src/orbit_watch/data/stations/`](../core/src/orbit_watch/data/stations).
All are simulated; the station coordinates are illustrative.

| Profile | Station | Kind | Angle noise | Timing |
|---|---|---|---|---|
| `sim-cmos-gps` | SIM-ESPOO | CMOS camera, GPS timing, RA/Dec | 5″ | 0.005 s |
| `sim-clock-offset` | SIM-TAMPERE | as above, clock 0.25 s ahead | 4″ | 0.01 s |
| `sim-visual-binoculars` | SIM-OULU | visual observer, RA/Dec | 900″ | 0.3 s |
| `sim-azel-mount` | SIM-KUOPIO | tracking mount, Az/El | 30″ | 0.02 s |

A new profile is a JSON file following
[`station-profile-1.0.schema.json`](../core/src/orbit_watch/schemas/station-profile-1.0.schema.json);
pass its path to `--profile`.

## Simulated objects

[`core/src/orbit_watch/data/catalog.json`](../core/src/orbit_watch/data/catalog.json)
holds four simulated objects. Their catalogue numbers come from the far end of
the Alpha-5 range (339001–339009, written Z9001–Z9009), far from the numbers
in use in 2026.

| Number | Name | Role |
|---|---|---|
| 339001 | SIM-CUBESAT-A | the requested object in the demo |
| 339002 | SIM-CUBESAT-B | same orbit, about 8 s behind A: the post-deployment mix-up |
| 339003 | SIM-ROCKET-BODY | another object for the quality meter |
| 339009 | SIM-RESTRICTED-PAYLOAD | **not** on the allow-list: requests for it are refused |

## The six test datasets

`orbit-watch demo` builds one delivery per scenario for the request "observe
SIM-CUBESAT-A on the night of 1–2 November 2026" (15:00–03:00 UTC, evening and
night in Finland) and verifies each. The simulated objects cross the equator
northwards at about 19:30 local time, so their two evening passes, at about 15:45
and 17:20 UTC, are lit under a dark sky; their later passes are in the Earth's
shadow. The committed output is in
[`examples/simulated/`](../examples/simulated).

| Dataset | Built how | Expected |
|---|---|---|
| `acceptable` | `sim-cmos-gps`, two passes | pass |
| `invalid` | the acceptable file, broken: a missing time, a declination of 95.5°, an unknown angle type | fail: `format` |
| `late` | observed one day after the window | fail: `time_window`, `min_observations` |
| `duplicate` | the acceptable observations delivered again | fail: `duplicates` |
| `wrong_target` | positions of SIM-CUBESAT-B labelled as SIM-CUBESAT-A | fail: `orbit_residuals` |
| `too_imprecise` | `sim-visual-binoculars` | fail: `declared_uncertainty` |
