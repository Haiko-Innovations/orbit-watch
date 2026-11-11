# Optimistic verification

Phase 1, step 1.3. Code: [`core/src/orbit_watch/service.py`](../core/src/orbit_watch/service.py)
and [`core/src/orbit_watch/reviewers.py`](../core/src/orbit_watch/reviewers.py).

Most deliveries need no human. The automated result is published, and it
becomes final unless someone with a stake challenges it in time. Only then do
people look at it.

## The flow

1. **Delivery.** A station delivers an observation file. The service keeps it
   by its SHA-256 and runs the [automated verification](verification.md) at
   once, with the request, the reference orbits, the allow-list and all earlier
   deliveries (for duplicate detection).
2. **Published result.** The report is stored by its SHA-256 and attested
   (`automated_verification`).
   - `pass` or `fail`: the **challenge period** starts (24 hours by default,
     fixed in the request's terms).
   - `inconclusive`: there is nothing to accept or reject automatically, so a
     reviewer round starts at once.
3. **No challenge.** When the challenge period ends, the automated result is
   final: `pass` becomes accepted, `fail` becomes rejected.
4. **Challenge.** The requester or the observer can challenge, with a reason.
   Three reviewers are chosen (below). Two equal votes decide; every vote
   carries a reason and is attested (`review_vote`).
5. **Dispute.** No two-of-three majority by the review deadline (48 hours by
   default) is a dispute.
6. **Settlement.** Every outcome is settled at once by the shared
   [settlement rules](settlement.md): completed reviews are paid whatever the
   outcome, a dispute pays the completed reviews, gives the observer nothing and
   refunds the rest. Nothing is ever locked.

The service takes the time from its callers. `tick(now)` applies passed
deadlines to every request and settles finished ones. With `open_service` the
state is stored in SQLite and files ([storage.md](storage.md), step 1.5); the
HTTP API comes in step 1.6.

## Who reviews

Reviewers are **pre-approved** and listed in a registry
([schema](../core/src/orbit_watch/schemas/reviewer-registry-1.0.schema.json),
[simulated example](../core/src/orbit_watch/data/reviewers.json)). A reviewer
can declare **affiliations**: parties whose requests and deliveries they must
never review, such as their own stations or their employer.

For a round, the eligible reviewers are those who are not the requester, the
observer or the challenger, and are not affiliated with any of them. The three
with the lowest score

```
SHA-256("orbit-watch-reviewers/1|" + request id + "|" + delivery SHA-256 + "|" + round + "|" + reviewer id)
```

are chosen. Nobody picks them, not even the challenger; the choice is fixed by
the delivery itself, it spreads work evenly over the registry, and anyone can
recompute it. If fewer than three independent reviewers exist, the challenge is
refused (`not_enough_reviewers`) and the request stays in its challenge period.

## Rules fixed in this step

- One reviewer round per request.
- A rejected delivery ends the request; it does not re-open for other
  stations. The challenge-round reserve pays exactly one round, and the books
  stay simple. The requester can open a new request.
- Challenges and votes must give reasons. They are part of the request's
  public record.

See [decision D-13](decisions.md#d-13-optimistic-verification-rules).

## Not yet

- Reviewers see real and known-answer calibration tasks in one queue; their
  accuracy is measured (step 1.4, [reviewer-accuracy.md](reviewer-accuracy.md)).
- Bonds for challengers and reviewers (an open question of the plan).
- Signed votes: EAS attestations in phase 2. In phase 1 the API keys of step
  1.6 identify reviewers.
