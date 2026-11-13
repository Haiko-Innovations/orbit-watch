# Data publication

Phase 1, step 1.8. Code: the publication part of
[`service.py`](../core/src/orbit_watch/service.py) and the `/v1/public/…`
routes of the [API](api.md).

Observations made for Orbit Watch requests are open data. A request's files
become public under **CC BY 4.0** once the request is settled and its embargo
has passed.

## Rules

| Rule | Detail |
|---|---|
| Licence | CC BY 4.0 (`https://creativecommons.org/licenses/by/4.0/`), fixed in the request's terms. |
| Embargo | 0 to 30 days, chosen by the requester in the terms ([P-07](decisions.md#p-07-default-time-limits-fixed-in-the-request-terms)). It runs from the moment the request is **settled**, so the outcome is always known before the data is public. |
| What is published | The request document, the observation file and the automated verification report. An expired or cancelled request without a delivery publishes only its request. |
| Before publication | Only the parties of the request (requester, observer, the reviewers of its round) and administrators can download its files and report. The request document is also open to any party while the request is opened or funded, and to the station that reserved it ([D-30](decisions.md#d-30-the-observers-view)). Everyone else gets `404`, so the API does not reveal what exists. |
| Calibration files | Never public. Only the reviewer who received the calibration task (and administrators) can download them. |
| Retention | Files are kept by SHA-256 and never deleted ([storage.md](storage.md)). |
| Permanent URL | `/v1/public/files/{sha256}`. The address is the content's hash, so it never changes and always returns the same bytes. Responses carry `Link: <licence URL>; rel="license"` and are cacheable forever. |
| Attribution | Every publication names the observer, the requester and the request, for example "Observations by station:SIM-ESPOO for requester:sim-cubesat-team, request SIM-REQ-0001, published through Orbit Watch". |

## Reading published data

Without any key:

```sh
orbit-watch public list --api http://127.0.0.1:8000
orbit-watch public get SIM-REQ-1001 --api http://127.0.0.1:8000 --download ./data
```

`public get --download` checks every file against its SHA-256 and writes the
licence and attribution next to the files.

| Endpoint | Returns |
|---|---|
| `GET /v1/public/requests` | every published request: state, licence, attribution, public-from time, file URLs |
| `GET /v1/public/requests/{id}` | one published request and its outcome (404 while embargoed) |
| `GET /v1/public/files/{sha256}` | a published file |

## Open points

- A requester cannot choose another licence yet (for example CC0).
- Personal data: station coordinates are part of every observation file. The
  terms that observers accept before phase 1 runs with real people must say
  that these become public, or the coordinates must be rounded first.
