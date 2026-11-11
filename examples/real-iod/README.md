# Real IOD observations with the quality meter

> **Status:** this repository does not yet contain a real observation example.
> See "Why there is no file here yet" below. The steps work with any real IOD
> file of a civilian object.

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
   orbit-watch fetch-gp --catnr 25544 -o gp.json
   ```

   The epoch must be within 7 days of the observations. CelesTrak offers only
   current element sets by URL, so use recent observations.
4. **Score.**

   ```sh
   orbit-watch score-station obs.iod --sites sites.json --catalog gp.json
   ```

## Why there is no file here yet

- Orbit Watch only handles civilian objects. Almost all IOD observations posted
  to SeeSat-L in October and November 2026 are of classified objects. They have
  no public orbit, and the project does not handle them.
- A committed example also needs the matching element set from the time of
  the observations. CelesTrak provides historical element sets only through a
  form, and its pages state no redistribution terms.
- IOD posts include the observer's station coordinates, which often point to a
  home. Committing them needs the observer's permission.

The plan is to ask an observer for a short IOD set of a civilian object (for
example a CubeSat), with permission to publish it under CC BY 4.0 together
with the element set used.
