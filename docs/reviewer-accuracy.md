# Reviewer accuracy

Phase 1, step 1.4. Code: [`core/src/orbit_watch/calibration.py`](../core/src/orbit_watch/calibration.py)
and the reviewer task part of [`service.py`](../core/src/orbit_watch/service.py).

Reviewers are paid for every completed review, whatever their answer. Without
a check, approving everything would be the easiest way to earn. Orbit Watch
therefore mixes **known-answer calibration tasks** into every reviewer's work
and shows each reviewer's accuracy on their profile.

## How it works

1. When a reviewer is assigned to a real reviewer round, the service also
   creates calibration tasks for them (one per assignment by default).
2. A calibration task is a SIMULATED delivery with a known correct answer:

   | Kind | What it is | Automated result | Correct answer |
   |---|---|---|---|
   | `correct_target` | the station observed the requested object | pass | approve |
   | `wrong_target` | the positions belong to the neighbouring object in the same orbit | fail | reject |

   Kinds are balanced per reviewer, so always giving the same answer scores
   about 50 %.
3. Reviewers see **one queue** (`assignments`). Real and calibration tasks have
   the same fields: an opaque task id, the request, the observation file and the
   automated report (all by SHA-256), the automated verdict, the challenge
   reason and the deadline. They answer every task the same way (`review`),
   with a reason. The answer never says whether the task was real.
4. Calibration answers move no points and do not affect any request.

## The profile

`reviewer_profile(reviewer)` shows:

| Field | Meaning |
|---|---|
| `calibration.answered`, `correct`, `accuracy` | Answers to calibration tasks and the share that was right. |
| `calibration.missed`, `open` | Calibration tasks past their deadline without an answer, and those still open. |
| `votes.approval_rate` | Share of approvals over all answers, real and calibration. |
| `votes.agreed_with_outcome` | In real rounds that were decided, how often the reviewer voted with the result. Real rounds have no known answer, so this is information only. |

Flags:

- `low_accuracy`: at least 5 calibration answers and accuracy below 80 %;
- `approves_almost_everything`: at least 10 answers and 95 % or more of them approvals;
- `missed_tasks`: calibration tasks left unanswered past their deadline.

In phase 1 the profile is information for the maintainers who approve
reviewers. It does not change reviewer selection or payments; see
[decision D-14](decisions.md#d-14-reviewer-accuracy).

## Limits of the prototype

- **Only simulated data.** In phase 1 every delivery is simulated, so
  calibration tasks look exactly like real ones. With real observations,
  calibration tasks must be **archived real deliveries with settled answers**,
  otherwise the `simulated` label would give them away.
- Calibration challenge reasons come from a short list of stock sentences, and
  rounds that start from an inconclusive automated result are always real.
  An attentive reviewer could notice either.
- Calibration answers are not attested in the journal. When attestations become
  public (EAS in phase 2), a missing attestation would reveal a calibration task.
- Calibration reviews are not paid. Whether they should be, and from which
  budget, is open.

These are recorded as open questions for the API (step 1.6) and phase 2.
