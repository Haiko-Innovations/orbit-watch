"""The request lifecycle state machine (phase 1, step 1.1)."""

import contextlib
import random
from datetime import timedelta

import pytest
from helpers import request_bytes

from orbit_watch import lifecycle as lc
from orbit_watch.lifecycle import Status, TransitionError
from orbit_watch.timeutil import parse_utc

T0 = parse_utc("2026-11-01T12:00:00Z")
REQUESTER = "requester:alice"
STATION = "station:SIM-ESPOO"
OTHER_STATION = "station:SIM-TAMPERE"
REVIEWERS = ("reviewer:r1", "reviewer:r2", "reviewer:r3")
SHA = "a" * 64
SPLIT = lc.RewardSplit(observer=100, reviewer=10)
PARTIES = [
    REQUESTER,
    "station:SIM-ESPOO",
    "station:SIM-TAMPERE",
    "reviewer:r1",
    "reviewer:r2",
    "reviewer:r3",
]


def minutes(n: float):
    return T0 + timedelta(minutes=n)


def make_terms(**changes):
    values = dict(
        request_id="SIM-REQ-0001",
        request_sha256=SHA,
        requester=REQUESTER,
        target_norad_id=339001,
        window_start=parse_utc("2026-11-01T15:00:00Z"),
        window_end=parse_utc("2026-11-02T03:00:00Z"),
        delivery_deadline=parse_utc("2026-11-03T03:00:00Z"),
    )
    values.update(changes)
    return lc.Terms(**values)


def run(*events, terms=None):
    record = lc.create(terms or make_terms(), T0)
    for event in events:
        record = lc.apply(record, event)
    return record


# Event sequences that reach every status (times in minutes after T0).
PATHS = {
    Status.DRAFT: [],
    Status.OPEN: [lc.Open(minutes(1))],
    Status.FUNDED: [lc.Open(minutes(1)), lc.Fund(minutes(2), SPLIT)],
    Status.RESERVED: [lc.Open(minutes(1)), lc.Reserve(minutes(3), STATION)],
    Status.DELIVERED: [
        lc.Open(minutes(1)),
        lc.Reserve(minutes(3), STATION),
        lc.Deliver(minutes(900), STATION, SHA),
    ],
    Status.CHALLENGE_PERIOD: [
        lc.Open(minutes(1)),
        lc.Reserve(minutes(3), STATION),
        lc.Deliver(minutes(900), STATION, SHA),
        lc.RecordVerification(minutes(910), "pass", SHA),
    ],
    Status.IN_REVIEW: [
        lc.Open(minutes(1)),
        lc.Reserve(minutes(3), STATION),
        lc.Deliver(minutes(900), STATION, SHA),
        lc.RecordVerification(minutes(910), "pass", SHA),
        lc.Challenge(minutes(920), REQUESTER, REVIEWERS),
    ],
}
PATHS[Status.ACCEPTED] = [
    *PATHS[Status.IN_REVIEW],
    lc.Vote(minutes(930), REVIEWERS[0], True),
    lc.Vote(minutes(931), REVIEWERS[1], True),
]
PATHS[Status.REJECTED] = [
    *PATHS[Status.IN_REVIEW],
    lc.Vote(minutes(930), REVIEWERS[0], False),
    lc.Vote(minutes(931), REVIEWERS[1], False),
]
PATHS[Status.DISPUTED] = [
    *PATHS[Status.IN_REVIEW],
    lc.Vote(minutes(930), REVIEWERS[0], True),
    lc.Vote(minutes(931), REVIEWERS[1], False),
]
PATHS[Status.EXPIRED] = [lc.Open(minutes(1))]
PATHS[Status.CANCELLED] = [lc.Open(minutes(1)), lc.Cancel(minutes(2), REQUESTER)]
PATHS[Status.SETTLED] = [*PATHS[Status.CANCELLED], lc.Settle(minutes(3))]


def reach(status: Status) -> lc.RequestRecord:
    record = run(*PATHS[status])
    if status is Status.DISPUTED:
        record = lc.advance(record, record.review_deadline)
    if status is Status.EXPIRED:
        record = lc.advance(record, record.terms.delivery_deadline)
    assert record.status is status
    return record


def valid_event(kind, record: lc.RequestRecord):
    """An event of this kind whose content is valid for the record."""
    at = record.updated_at + timedelta(seconds=1)
    return {
        lc.ReviseTerms: lambda: lc.ReviseTerms(at, make_terms(embargo_days=7)),
        lc.Open: lambda: lc.Open(at),
        lc.Fund: lambda: lc.Fund(at, SPLIT),
        lc.Reserve: lambda: lc.Reserve(at, STATION),
        lc.Deliver: lambda: lc.Deliver(at, record.reserved_by or STATION, SHA),
        lc.RecordVerification: lambda: lc.RecordVerification(at, "fail", SHA),
        lc.Challenge: lambda: lc.Challenge(at, REQUESTER, REVIEWERS),
        lc.Vote: lambda: lc.Vote(at, REVIEWERS[2], True),
        lc.Cancel: lambda: lc.Cancel(at, REQUESTER),
        lc.Settle: lambda: lc.Settle(at),
    }[kind]()


EVENT_KINDS = [
    lc.ReviseTerms,
    lc.Open,
    lc.Fund,
    lc.Reserve,
    lc.Deliver,
    lc.RecordVerification,
    lc.Challenge,
    lc.Vote,
    lc.Cancel,
    lc.Settle,
]


@pytest.mark.parametrize("status", list(Status), ids=str)
@pytest.mark.parametrize("kind", EVENT_KINDS, ids=lambda k: k.__name__)
def test_every_status_and_event(status, kind):
    """Allowed events succeed; every other event is refused with a clear error."""
    record = reach(status)
    event = valid_event(kind, record)
    if kind in lc.ALLOWED[status]:
        lc.apply(record, event)
    else:
        with pytest.raises(TransitionError) as error:
            lc.apply(record, event)
        assert error.value.code == "forbidden_in_status"
        assert str(status) in str(error.value)


def test_allowed_table_covers_every_status():
    assert set(lc.ALLOWED) == set(Status)
    assert lc.ALLOWED[Status.SETTLED] == ()


def test_unchallenged_pass_is_accepted_and_settled():
    record = reach(Status.CHALLENGE_PERIOD)
    assert record.challenge_deadline == minutes(910) + timedelta(hours=24)
    record = lc.advance(record, record.challenge_deadline)
    assert record.status is Status.ACCEPTED and "nobody challenged" in record.outcome_reason
    record = lc.apply(record, lc.Settle(record.updated_at))
    assert record.status is Status.SETTLED and record.outcome is Status.ACCEPTED


def test_unchallenged_fail_is_rejected():
    record = run(*PATHS[Status.DELIVERED], lc.RecordVerification(minutes(910), "fail", SHA))
    record = lc.advance(record, minutes(910 + 24 * 60))
    assert record.status is Status.REJECTED


def test_inconclusive_result_goes_straight_to_reviewers():
    record = run(
        *PATHS[Status.DELIVERED],
        lc.RecordVerification(minutes(910), "inconclusive", SHA, REVIEWERS),
    )
    assert record.status is Status.IN_REVIEW
    assert record.review_deadline == minutes(910) + timedelta(hours=48)
    with pytest.raises(TransitionError) as error:
        run(*PATHS[Status.DELIVERED], lc.RecordVerification(minutes(910), "inconclusive", SHA))
    assert error.value.code == "invalid_reviewers"


@pytest.mark.parametrize(
    ("votes", "expected"),
    [
        ((True, True), Status.ACCEPTED),
        ((False, False), Status.REJECTED),
        ((True, False, True), Status.ACCEPTED),
        ((False, True, False), Status.REJECTED),
    ],
)
def test_two_of_three_decides(votes, expected):
    record = reach(Status.IN_REVIEW)
    for index, approve in enumerate(votes):
        record = lc.apply(record, lc.Vote(minutes(930 + index), REVIEWERS[index], approve))
    assert record.status is expected
    assert len(record.votes) == len(votes)


def test_no_majority_by_the_deadline_is_a_dispute():
    record = reach(Status.IN_REVIEW)
    record = lc.apply(record, lc.Vote(minutes(930), REVIEWERS[0], True))
    record = lc.advance(record, record.review_deadline + timedelta(days=10))
    assert record.status is Status.DISPUTED
    assert record.history[-1].at == record.review_deadline  # applied at the deadline itself
    # A dispute never stays open: it can always be settled.
    assert lc.apply(record, lc.Settle(record.updated_at)).status is Status.SETTLED


def test_late_vote_is_refused():
    record = reach(Status.IN_REVIEW)
    with pytest.raises(TransitionError) as error:
        lc.apply(record, lc.Vote(record.review_deadline + timedelta(seconds=1), REVIEWERS[0], True))
    assert error.value.code == "forbidden_in_status"


def test_reservation_lapses_and_another_station_can_reserve():
    terms = make_terms(reservation_hours=2)
    record = run(
        lc.Open(minutes(1)),
        lc.Fund(minutes(2), SPLIT),
        lc.Reserve(minutes(3), STATION),
        terms=terms,
    )
    assert record.reservation_expires_at == minutes(123)
    with pytest.raises(TransitionError):
        lc.apply(record, lc.Deliver(minutes(124), STATION, SHA))
    record = lc.advance(record, minutes(124))
    assert record.status is Status.FUNDED and record.reserved_by is None
    record = lc.apply(record, lc.Reserve(minutes(130), OTHER_STATION))
    assert record.reserved_by == OTHER_STATION


def test_reservation_never_outlives_the_delivery_deadline():
    record = run(lc.Open(minutes(1)), lc.Reserve(parse_utc("2026-11-02T20:00:00Z"), STATION))
    assert record.reservation_expires_at == record.terms.delivery_deadline
    record = lc.advance(record, record.terms.delivery_deadline)
    assert record.status is Status.EXPIRED
    assert [h.event for h in record.history[-2:]] == [
        "reservation_lapsed",
        "delivery_deadline_passed",
    ]


def test_no_delivery_expires_and_stuck_verification_expires():
    assert reach(Status.EXPIRED).outcome_reason == "no delivery before the deadline"
    record = reach(Status.DELIVERED)
    record = lc.advance(record, minutes(900) + timedelta(hours=24))
    assert record.status is Status.EXPIRED and "verification" in record.outcome_reason


@pytest.mark.parametrize(
    ("events", "code"),
    [
        ([lc.Open(minutes(1)), lc.Reserve(minutes(2), REQUESTER)], "conflict_of_interest"),
        (
            [
                lc.Open(minutes(1)),
                lc.Reserve(minutes(2), STATION),
                lc.Deliver(minutes(3), OTHER_STATION, SHA),
            ],
            "not_reserved_by_station",
        ),
        ([lc.Open(minutes(1)), lc.Fund(minutes(2), lc.RewardSplit(0, 0))], "invalid_amount"),
        ([lc.Open(minutes(1)), lc.Cancel(minutes(2), STATION)], "not_requester"),
        (
            [
                *PATHS[Status.CHALLENGE_PERIOD],
                lc.Challenge(minutes(920), "someone:else", REVIEWERS),
            ],
            "not_a_party",
        ),
        (
            [
                *PATHS[Status.CHALLENGE_PERIOD],
                lc.Challenge(minutes(920), STATION, ("reviewer:r1", "reviewer:r2", STATION)),
            ],
            "conflict_of_interest",
        ),
        (
            [
                *PATHS[Status.CHALLENGE_PERIOD],
                lc.Challenge(
                    minutes(920), REQUESTER, ("reviewer:r1", "reviewer:r1", "reviewer:r2")
                ),
            ],
            "invalid_reviewers",
        ),
        ([*PATHS[Status.IN_REVIEW], lc.Vote(minutes(930), "reviewer:r9", True)], "not_assigned"),
        (
            [
                *PATHS[Status.IN_REVIEW],
                lc.Vote(minutes(930), REVIEWERS[0], True),
                lc.Vote(minutes(931), REVIEWERS[0], True),
            ],
            "already_voted",
        ),
        (
            [*PATHS[Status.DELIVERED], lc.RecordVerification(minutes(910), "maybe", SHA)],
            "invalid_verdict",
        ),
        ([lc.Open(minutes(1)), lc.Fund(minutes(0), SPLIT)], "out_of_order"),
    ],
)
def test_guards(events, code):
    with pytest.raises(TransitionError) as error:
        run(*events)
    assert error.value.code == code


def test_observer_can_challenge_a_rejection():
    record = run(
        *PATHS[Status.DELIVERED],
        lc.RecordVerification(minutes(910), "fail", SHA),
        lc.Challenge(minutes(911), STATION, REVIEWERS, "the reference orbit is old"),
    )
    assert record.status is Status.IN_REVIEW and record.challenger == STATION


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"embargo_days": 31}, "embargo"),
        ({"delivery_deadline": parse_utc("2026-11-01T20:00:00Z")}, "delivery deadline"),
        ({"challenge_period_hours": 0}, "challenge_period_hours"),
    ],
)
def test_invalid_terms_cannot_open(changes, message):
    with pytest.raises(TransitionError, match=message):
        run(lc.Open(minutes(1)), terms=make_terms(**changes))


def test_terms_are_frozen_when_the_request_opens():
    record = run(lc.ReviseTerms(minutes(1), make_terms(embargo_days=14)), lc.Open(minutes(2)))
    assert record.terms.embargo_days == 14
    assert record.terms_sha256 == record.terms.sha256()
    with pytest.raises(TransitionError):
        lc.apply(record, lc.ReviseTerms(minutes(3), make_terms()))


def test_terms_from_a_request_document():
    terms = lc.terms_from_request(request_bytes(), REQUESTER)
    assert terms.target_norad_id == 339001
    assert terms.delivery_deadline == terms.window_end + timedelta(hours=24)
    assert terms.challenge_period_hours == 24 and terms.reservation_hours == 72
    assert terms.review_hours == 48 and terms.embargo_days == 0
    assert terms.licence == "CC-BY-4.0"
    assert len(terms.sha256()) == 64 and terms.sha256() == terms.sha256()


def test_advance_is_idempotent_and_needs_ordered_time():
    record = reach(Status.CHALLENGE_PERIOD)
    later = minutes(5000)
    once = lc.advance(record, later)
    assert lc.advance(once, later) == once
    assert lc.advance(lc.advance(record, minutes(2000)), later) == once
    with pytest.raises(TransitionError) as error:
        lc.advance(once, minutes(1))
    assert error.value.code == "out_of_order"


def test_records_serialise_deterministically():
    a = reach(Status.ACCEPTED).to_document()
    b = reach(Status.ACCEPTED).to_document()
    assert a == b
    assert a["status"] == "accepted" and a["outcome_reason"] == "reviewers approved 2-0"
    assert [h["event"] for h in a["history"]][:3] == ["create", "open", "reserve"]


def random_event(kind, now, rng, parties):
    if kind is lc.ReviseTerms:
        return lc.ReviseTerms(now, make_terms(embargo_days=rng.randint(0, 30)))
    if kind is lc.Fund:
        return lc.Fund(now, lc.RewardSplit(rng.randint(1, 100), rng.randint(0, 10)))
    if kind is lc.Reserve:
        return lc.Reserve(now, rng.choice(parties))
    if kind is lc.Deliver:
        return lc.Deliver(now, rng.choice(parties), SHA)
    if kind is lc.RecordVerification:
        verdict = rng.choice(["pass", "fail", "inconclusive"])
        return lc.RecordVerification(now, verdict, SHA, tuple(rng.sample(parties, 3)))
    if kind is lc.Challenge:
        return lc.Challenge(now, rng.choice(parties), tuple(rng.sample(parties, 3)))
    if kind is lc.Vote:
        return lc.Vote(now, rng.choice(parties), rng.random() < 0.5)
    if kind is lc.Cancel:
        return lc.Cancel(now, rng.choice(parties))
    return kind(now)  # Open, Settle


@pytest.mark.parametrize("seed", range(150))
def test_random_event_sequences_keep_the_invariants(seed):
    rng = random.Random(seed)
    parties = [REQUESTER, STATION, OTHER_STATION, *REVIEWERS]
    record = lc.create(make_terms(reservation_hours=rng.choice([1, 12, 72])), T0)
    now = T0
    terms_hash = None
    for _ in range(40):
        now += timedelta(minutes=rng.choice([1, 10, 60, 600, 3000]))
        kind = rng.choice(EVENT_KINDS)
        event = random_event(kind, now, rng, parties)
        before = record
        try:
            record = lc.apply(record, event)
        except TransitionError:
            assert record == before  # a refused event changes nothing
            continue
        # Invariants after every accepted event.
        times = [h.at for h in record.history]
        assert times == sorted(times)
        if record.terms_sha256 is not None:
            terms_hash = terms_hash or record.terms_sha256
            assert record.terms_sha256 == terms_hash == record.terms.sha256()
        if record.outcome is not None:
            assert record.status in (*lc.OUTCOMES, Status.SETTLED)
        assert record.observer is None or record.observer != record.requester
        assert not set(record.reviewers) & {record.requester, record.observer}
        if before.status is Status.SETTLED:
            pytest.fail("a settled request changed")
    # Every request that left draft reaches an outcome once enough time has passed.
    record = lc.advance(record, now + timedelta(days=60))
    assert record.status in (Status.DRAFT, Status.SETTLED, *lc.OUTCOMES)
    if record.status in lc.OUTCOMES:
        assert lc.apply(record, lc.Settle(record.updated_at)).status is Status.SETTLED


def test_documentation_has_the_current_diagram(repo_root):
    text = (repo_root / "docs" / "lifecycle.md").read_text()
    assert lc.mermaid_diagram() in text


def test_diagram_matches_the_rules():
    diagram = lc.mermaid_diagram()
    for status in Status:
        assert f" {status} " in diagram or f" {status}:" in diagram or f"{status} -->" in diagram
    event_kinds = {
        "open": lc.Open,
        "cancel": lc.Cancel,
        "fund": lc.Fund,
        "reserve": lc.Reserve,
        "deliver": lc.Deliver,
        "challenge": lc.Challenge,
        "settle": lc.Settle,
    }
    for line in diagram.splitlines()[2:-1]:
        source, rest = line.strip().split(" --> ")
        label = rest.split(": ", 1)[1]
        if label in event_kinds:
            assert event_kinds[label] in lc.ALLOWED[Status(source)], line


@pytest.mark.parametrize(
    ("split", "message"),
    [
        (lc.RewardSplit(-1, 5), "observer"),
        (lc.RewardSplit(10, 1.5), "reviewer"),
        (lc.RewardSplit(0, 0, 0), "at least one point"),
    ],
)
def test_invalid_split_is_refused(split, message):
    with pytest.raises(TransitionError, match=message):
        run(lc.Open(minutes(1)), lc.Fund(minutes(2), split))


def test_split_is_locked_at_funding():
    record = reach(Status.FUNDED)
    assert record.split == SPLIT and record.funded_points == 100 + 3 * 10
    assert record.to_document()["split"]["challenge_reserve"] == 30


@pytest.mark.parametrize("status", list(Status), ids=str)
def test_records_survive_a_json_round_trip(status):
    import json

    record = reach(status)
    text = json.dumps(record.to_document())
    assert lc.record_from_document(json.loads(text)) == record


@pytest.mark.parametrize("seed", range(40))
def test_random_records_survive_a_round_trip(seed):
    import json

    rng = random.Random(seed)
    record = lc.create(make_terms(), T0)
    now = T0
    for _ in range(25):
        now += timedelta(minutes=rng.choice([1, 60, 900]))
        with contextlib.suppress(TransitionError):
            record = lc.apply(record, random_event(rng.choice(EVENT_KINDS), now, rng, PARTIES))
        restored = lc.record_from_document(json.loads(json.dumps(record.to_document())))
        assert restored == record
