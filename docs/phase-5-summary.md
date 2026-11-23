# Phase 5 summary

Phase 5 is complete as **version 0.6.0**: real orbits and real observations on the
testnet. This is the end-of-phase summary that the [plan](plan.md#8-deliverables)
asks for.

> **Testnet only, no real value.** The service runs at
> <https://orbit-watch-tan.vercel.app> on Base Sepolia, with Circle's testnet USDC,
> which has no value. SIMULATED and real data run side by side, and every object,
> reference orbit and observation says which it is.

## What works

- **Real reference orbits in the core and the service** (5.1, 5.4;
  [D-44](decisions.md#d-44-reference-orbits-in-the-core),
  [D-47](decisions.md#d-47-reference-orbits-in-the-service),
  [D-48](decisions.md#d-48-the-follower-fetches-reference-orbits)):
  - A catalogue holds several element sets of an object, and verification uses the
    one nearest the observations (method 2.1.0). The report names it by its source,
    epoch and SHA-256, never the set itself.
  - The follower fetches open requests' objects from CelesTrak, one at a time and at
    most once per update. A replay's set comes from the IAU CPS's SatChecker.
  - The first answer that is not 200 stops the source until a person resumes it, and
    the hourly uptime check reports it.
  - No real element set is in the repository: examples name their sets in
    manifests, and one command fills a cache outside it.
- **Real observations from SCORE** (5.2;
  [D-45](decisions.md#d-45-real-observations-from-score)). 18 tracks from 7
  instruments are in [`examples/real/`](../examples/real), and 38 more are in the
  validation set. All are credited to their observers by ORCID iD under CC BY 4.0,
  with the statements SCORE and SatChecker ask for.
- **The method measured on real data** (5.3;
  [D-46](decisions.md#d-46-the-method-measured-on-real-data),
  [real-data-validation.md](real-data-validation.md)). Method 2.1.0 was measured
  unchanged on 56 real tracks, with faults put into copies of them, and the
  measurement is reproducible with one command. Real tracks are in the known-answer
  datasets. Changes the measurement suggests are left for decisions of their own.
- **Real objects on the allow-list** (5.4;
  [D-49](decisions.md#d-49-real-objects-on-the-allow-list)):
  - CelesTrak's groups `science`, `education`, `amateur` and `cubesat` are on the
    list, without the groups `military` and `radar` and without names that suggest
    military payloads. They are fetched once a day.
  - An administrator adds other objects with a public reason.
  - Production has listed 203 real objects since 2026-11-22.
- **Real and simulated side by side** (5.5;
  [D-50](decisions.md#d-50-simulated-stations-on-real-objects) to
  [D-53](decisions.md#d-53-a-stand-in-for-a-real-object-in-the-local-stack)):
  - Simulated stations observe real objects along their stored element sets.
  - An administrator creates replays of published observations. A replay station
    delivers them under the observers' names, and is paid on the testnet.
  - Every page labels objects, reference orbits and observations by their source.
    The testnet label and the terms of use no longer say that all data is
    SIMULATED, and a data sources page credits CelesTrak, SatChecker and SCORE.
- **The station's place** (5.6;
  [D-54](decisions.md#d-54-the-observer-chooses-how-precisely-the-place-is-published),
  [D-55](decisions.md#d-55-the-profile-is-the-stations-place-for-every-format)):
  - The observer chooses whether the place is published exactly or to about a
    kilometre, with neither chosen in advance, and can change the choice for later
    deliveries.
  - The profile is the station's place for every format: a JSON delivery from
    another place is refused, and IOD and TDM files are verified at the profile's
    place, which is published with them.
  - The privacy notice and the data inventory say so.
- **Visibility** (5.7; [D-56](decisions.md#d-56-the-suns-place-from-a-short-formula)
  to [D-58](decisions.md#d-58-a-stations-visible-passes-for-a-request),
  [visibility.md](visibility.md)):
  - The Sun's place comes from the US Naval Observatory's short formula. Against
    JPL's DE421 it is at most 55.9″ off over 1900–2049.
  - The simulator observes only objects lit by the Sun under a dark sky (issue
    [#7](https://github.com/Haiko-Innovations/orbit-watch/issues/7)). The SIMULATED
    orbits moved to the evening so that a station can see them.
  - A station sees its visible passes for a request.

## Real data end to end on Base Sepolia

Step 5.8 ran two requests through the public service with the testnet keystores of
[D-24](decisions.md#d-24-the-base-sepolia-deployment), so no person's own wallet was
needed. The requester, `requester:sim-cubesat-team`, funded each with 1.3 testnet USDC:
1 for the observer, 0.1 for each reviewer, and the rest held against a challenge. Each
request had a one-hour challenge period, and the follower settled both without anyone
calling `tick`.

### A replay of real SCORE observations

[REPLAY-58296-20240508](https://orbit-watch-tan.vercel.app/#/requests/REPLAY-58296-20240508)
replays 108 observations of PELICAN-1 (58296) that an observer, ORCID iD
[0000-0001-6659-9253](https://orcid.org/0000-0001-6659-9253), published in SCORE for
8 May 2024 under CC BY 4.0.

1. An administrator checked the object's owner in CelesTrak's satellite catalogue:
   payload 2023-174AS, owner US, launched 2023-11-11. It was added to the allow-list
   with a public reason, as a commercial Earth-imaging satellite of Planet Labs.
2. The administrator created the replay for the requester, naming the file by its
   SHA-256 and the new replay station `station:ORBIT-WATCH-REPLAY`.
3. Once the request was open, the follower fetched SatChecker's set nearest the
   window (epoch 2024-05-08 13:35 UTC), on its next run, 2026-11-22 17:45 UTC.
4. The replay station delivered the file as it was. The automated verification
   passed: all 108 observations within their limits, a median residual of 4.15′.
   Nothing was marked SIMULATED.
5. The follower settled it as accepted at 19:01 UTC. The replay station received
   1 USDC, and the requester got 0.3 USDC back.

### A real object with simulated observations

[SIM-REQ-27848-20261123](https://orbit-watch-tan.vercel.app/#/requests/SIM-REQ-27848-20261123)
asked simulated stations to observe CUBESAT XI-IV (CO-57, 27848). It is a real
object in CelesTrak's groups `amateur` and `cubesat`.

1. The object was chosen for a visible evening pass over SIM-ESPOO's place on
   2026-11-23. SIM-ESPOO's profile is kept to about a kilometre.
2. The follower fetched CelesTrak's current set from a day before the window. Before
   reserving, the station's pass list showed one visible pass, 15:27–15:35 UTC,
   82.8° high.
3. After the window, SIM-ESPOO simulated 8 observations through the service along the
   stored set (epoch 2026-11-23 00:03 UTC) and delivered them. The automated
   verification passed, with a median residual of 12.8″. The report says SIMULATED,
   since the observations are.
4. The follower settled it as accepted at 17:00 UTC, when the challenge period was
   over. SIM-ESPOO received 1 USDC, and the requester got 0.3 USDC back. The
   published files carry the SIMULATED label, and the object and its reference orbit
   are labelled real, from CelesTrak.

### How often CelesTrak could not be reached

Fetching has been on in production since 2026-11-22 05:47 UTC. Until this release,
CelesTrak and SatChecker answered every request with 200. Fetching never stopped, and
the reference-orbit health check stayed green. This counted the daily group
downloads, the objects of the two requests and the replay's past set.

### Found on the way, and fixed

- **[#130](https://github.com/Haiko-Innovations/orbit-watch/pull/130):** the labels of
  a request whose report was of format 1.0 failed. That broke the public page of the
  first settled request and the administrator's overview, which answered 500.
- **[#131](https://github.com/Haiko-Innovations/orbit-watch/pull/131):** a published
  replay's attribution named the replay station as the observer. It now names the
  observers, the source and the licence.

## Completion criteria

From [P5-15](decisions.md#p5-15-phase-5-completion-criteria):

| Criterion | Status |
|---|---|
| 1. Deliveries for real objects are verified against real reference orbits, CelesTrak's for current requests and SatChecker's for replays, with the set nearest the observations named in the report | ✅ Both requests above, in production. `test_reference_orbits_service.py`, `test_replays.py` |
| 2. Every fetch from CelesTrak, SatChecker and SCORE follows the source's rules, stops at the first answer that is not 200 and tells a person; tested against local stand-ins; no test in CI calls an outside service except to fill its cache | ✅ [D-48](decisions.md#d-48-the-follower-fetches-reference-orbits), `test_orbit_follower.py`, `test_allowlist_service.py`, `test_score.py`. CI fetches only the cache of real element sets |
| 3. A set of real SCORE observations is committed, credited under CC BY 4.0 with the statements the sources ask for; no real element set in the repository | ✅ [`examples/real/`](../examples/real), its CREDITS.md and the data sources page. `test_real_example.py` and `test_real_data_validation.py` check that no element set is committed |
| 4. The method's behaviour on real data is measured and published, reproducible with one command; real tracks in the known-answer datasets | ✅ [real-data-validation.md](real-data-validation.md), `orbit-watch measure-method` |
| 5. Real objects are on the allow-list under D-05's rules, and an administrator's additions show their reasons | ✅ [D-49](decisions.md#d-49-real-objects-on-the-allow-list). 203 objects from CelesTrak's groups, and PELICAN-1 with its reason |
| 6. Every page labels objects, reference orbits and observations by their source; SIMULATED on all simulated data and nothing else; the testnet label on every page; tested end to end | ✅ [D-52](decisions.md#d-52-labels-by-source-on-every-page), [D-53](decisions.md#d-53-a-stand-in-for-a-real-object-in-the-local-stack); `labels.spec.ts` and `public.spec.ts` |
| 7. Replays name their observers and never appear as them | ✅ [D-51](decisions.md#d-51-replays), #131. The replay's page, files and attribution name the observer; the replay station appears only as the one that replayed |
| 8. The observer chooses the place's precision with nothing chosen in advance; the profile is the place for every format, a delivery from another place refused, tested; the privacy notice and the data inventory say so | ✅ [D-54](decisions.md#d-54-the-observer-chooses-how-precisely-the-place-is-published), [D-55](decisions.md#d-55-the-profile-is-the-stations-place-for-every-format); `test_privacy.py`, `test_station_place.py`, `observer.spec.ts`. The notice's version is 22 November 2026 |
| 9. The simulator observes only objects the Sun lights under a dark sky; an observer sees the station's visible passes for a request | ✅ [D-57](decisions.md#d-57-the-simulator-observes-only-what-a-station-can-see), [D-58](decisions.md#d-58-a-stations-visible-passes-for-a-request); `test_passes.py`, `passes.spec.ts` |
| 10. On the public service, a replay of real observations and a request for a real object with simulated observations have both settled on Base Sepolia; every CI check passes; release 0.6.0 | ✅ Both requests above. CI passes: 1019 Python tests, 78 web unit tests and 54 end-to-end tests, run against the local stack and against the service image. This release |

## What is real, what is simulated, and what is a testnet

- **Real:**
  - the objects on the allow-list from CelesTrak's groups, and those an
    administrator adds;
  - their reference orbits, from CelesTrak and SatChecker;
  - the replayed observations from SCORE;
  - the stations' places, as precisely as their observers choose.
- **SIMULATED:** the service's own objects, the stations' instruments, observations
  that simulated stations make, and the reviewers. Each is labelled.
- **The money** is Circle's testnet USDC on Base Sepolia, of no value.
- **One maintainer still holds the network's keys**, as in phase 4: the Safe's
  signers, the verifier key, the testnet parties' keystores and the account behind
  the RPC endpoint.

## Follow-ups

These need the maintainer or someone outside the repository. They are not completion
criteria ([P5-14](decisions.md#p5-14-follow-ups-at-the-end-not-in-the-way)):
- telling SCORE that Orbit Watch uses its data
  ([#113](https://github.com/Haiko-Innovations/orbit-watch/issues/113));
- reading Space-Track's user agreement on redistributing element sets
  ([#114](https://github.com/Haiko-Innovations/orbit-watch/issues/114)).

The redesign of the web application
([#97](https://github.com/Haiko-Innovations/orbit-watch/issues/97)) and the screen
reader test after it ([D-42](decisions.md#d-42-the-screen-reader-test-after-the-redesign))
stay open.
