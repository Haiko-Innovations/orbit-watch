# Real IOD observations with the quality meter

> **A real example is in [`../real/`](../real):** observations that their observers
> published in SCORE under CC BY 4.0, in Orbit Watch's format (step 5.2, #8). The
> steps below work with any real IOD file of a civilian object.

## Steps

1. **Observations.** Save the IOD lines of one station in a text file, for
   example `obs.iod`. Copying from a web archive is fine: the reader handles
   non-breaking spaces and shifted columns, and lists every line it skips.
2. **Station coordinates.** IOD lines carry only a four-digit station number.
   Write a sites file with the coordinates the observer publishes:

   ```json
   {
     "format": "orbit-watch/sites",
     "format_version": "1.0",
     "sites": [
       {"id": "1234", "iod_station_number": 1234,
        "latitude_deg": 60.0, "longitude_deg": 25.0, "altitude_m": 50}
     ]
   }
   ```

3. **Reference orbit.** Download current GP data for the object (one request):

   ```sh
   orbit-watch fetch-gp --catnr 25544 -o gp.csv
   ```

   The epoch must be within 7 days of the observations. CelesTrak offers only
   current element sets by URL, so use recent observations.
4. **Score.**

   ```sh
   orbit-watch score-station obs.iod --sites sites.json --catalog gp.csv
   ```

## Why the real example is not in IOD

Until phase 5 there was no real example, for three reasons:
- almost all IOD observations posted to SeeSat-L in October and November 2026 are of
  classified objects, which Orbit Watch does not handle;
- an example needs the element set from the time of the observations, and CelesTrak
  gives historical element sets only through a form;
- IOD posts include the observer's coordinates, and committing them needs the
  observer's permission.

The IAU CPS's SCORE answers all three: civilian objects, past element sets from its
SatChecker, and observers who published their observations and places under CC BY 4.0
themselves. SCORE's observers have no IOD station numbers, so the example is in Orbit
Watch's format ([P5-06](../../docs/decisions.md#p5-06-real-observations-from-score)).
