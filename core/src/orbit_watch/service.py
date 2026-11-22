"""Optimistic verification: the request service (phase 1, step 1.3).

The service ties the parts together the way the phase 1 API will use them:

1. a station delivers an observation file; the service keeps it by its SHA-256
   and runs the automated verification engine at once;
2. the result is published and attested; ``pass`` and ``fail`` start the
   challenge period, ``inconclusive`` goes straight to reviewers;
3. if nobody challenges before the deadline, the automated result is final;
4. a challenge by the requester or the observer starts a reviewer round: three
   pre-approved, independent reviewers chosen by ``ReviewerRegistry.select``;
   two equal votes decide, and every vote carries a reason;
5. no majority by the review deadline is a dispute;
6. every outcome is settled at once through the settlement adapter, by the
   shared settlement rules.

The service takes the time from its callers (an injected clock, decision
P-05), so it is deterministic and easy to test. It keeps its working state in
memory; with ``open_service`` it also writes every change to SQLite and the
file store (step 1.5), one transaction per call. A refused call (any
``ServiceError``) changes nothing: the transaction is rolled back and the
state reloaded. The HTTP API comes in step 1.6.

On a testnet chain (step 2.6, ``open_service(..., chain=ChainLink(...))``) every
funded request lives on the escrow contract: its parties sign their own
transactions and the service follows the chain (``orbit_watch.chain.link``).
The calls below then refuse funded requests (``sign_on_chain``); unfunded
requests work as before.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from orbit_watch import allowlist, orbits
from orbit_watch import calibration as cal
from orbit_watch import lifecycle as lc
from orbit_watch.canonical import dumps_pretty, sha256_bytes
from orbit_watch.catalog import parse_catalog
from orbit_watch.documents import Replay, Request
from orbit_watch.formats import FormatError, Sites
from orbit_watch.lifecycle import RequestRecord, Status, TransitionError
from orbit_watch.reviewers import ReviewerError, ReviewerRegistry
from orbit_watch.settlement import SettlementAdapter, SettlementError, settlement_plan
from orbit_watch.storage import Storage, StoredFiles
from orbit_watch.timeutil import format_utc
from orbit_watch.verify.engine import PARAMETERS, UsageError, VerificationInput, verify

VERIFIER = "system:verifier"
PLATFORM = "platform:orbit-watch"
LICENCE_URLS = {"CC-BY-4.0": "https://creativecommons.org/licenses/by/4.0/"}


def _atomic[F: Callable[..., Any]](method: F) -> F:
    """One transaction per call when the service is stored; reload on failure."""

    @functools.wraps(method)
    def wrapper(self: RequestService, *args: Any, **kwargs: Any) -> Any:
        if self.storage is None or self.storage.db.in_transaction:
            # Without storage there is nothing to roll back; inside an outer
            # transaction (the API) the outer caller rolls back and reloads.
            return method(self, *args, **kwargs)
        try:
            with self.storage.db.transaction():
                return method(self, *args, **kwargs)
        except BaseException:
            self._reload()
            raise

    return wrapper  # type: ignore[return-value]


class ServiceError(ValueError):
    """A refused call. ``code`` is stable and maps to an API error later."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class VerificationContext:
    """What automated verification compares deliveries with."""

    catalog: bytes
    policy: bytes
    sites: Sites | None = None


@dataclass
class Delivered:
    """What the service keeps about one delivery."""

    request_id: str
    station: str
    observations_sha256: str
    observations_format: str | None
    report_sha256: str
    verdict: str


@dataclass
class RequestService:
    adapter: SettlementAdapter
    reviewers: ReviewerRegistry
    context: VerificationContext
    platform: str = PLATFORM
    records: dict[str, RequestRecord] = field(default_factory=dict)
    request_documents: dict[str, bytes] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)  # content-addressed by SHA-256
    deliveries: dict[str, Delivered] = field(default_factory=dict)  # by request id
    settlements: dict[str, dict[str, Any]] = field(default_factory=dict)  # by request id
    # Reviewer tasks (step 1.4). Task ids are opaque, so real tasks and known-answer
    # calibration tasks cannot be told apart.
    calibration_per_assignment: int = 1
    task_salt: str = "orbit-watch-tasks"
    real_tasks: dict[str, tuple[str, str]] = field(default_factory=dict)  # id -> request, reviewer
    calibration_tasks: dict[str, cal.CalibrationTask] = field(default_factory=dict)
    # Real element sets the service verifies against, by object (step 5.4, D-47).
    element_sets: dict[int, list[orbits.StoredSet]] = field(default_factory=dict)
    # Real objects on the allow-list (step 5.4, D-49): CelesTrak's groups as last fetched,
    # each {"fetched_at", "sha256", "members": {catalogue number: name}}, and an
    # administrator's additions, each {"name", "reason", "added_at", "added_by"}.
    allowlist_groups: dict[str, dict[str, Any]] = field(default_factory=dict)
    allowlist_additions: dict[int, dict[str, Any]] = field(default_factory=dict)
    _targets: dict[int, allowlist.Target] | None = field(default=None, repr=False)
    _replays: dict[str, Replay | None] = field(default_factory=dict, repr=False)
    storage: Storage | None = None
    # The testnet chain (step 2.6): an orbit_watch.chain.link.ChainLink, or None.
    chain: Any = None

    # ------------------------------------------------------------------ persistence

    def _save_record(self, record: RequestRecord) -> RequestRecord:
        self.records[record.request_id] = record
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO requests (request_id, requester, status, request_sha256, "
                "record_json, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (request_id) DO UPDATE SET status = excluded.status, "
                "record_json = excluded.record_json, updated_at = excluded.updated_at",
                (
                    record.request_id,
                    record.requester,
                    str(record.status),
                    sha256_bytes(self.request_documents[record.request_id]),
                    json.dumps(record.to_document(), sort_keys=True),
                    format_utc(record.updated_at),
                ),
            )
        return record

    def _save_delivery(self, delivered: Delivered) -> None:
        self.deliveries[delivered.request_id] = delivered
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO deliveries (request_id, station, observations_sha256, "
                "observations_format, report_sha256, verdict) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    delivered.request_id,
                    delivered.station,
                    delivered.observations_sha256,
                    delivered.observations_format,
                    delivered.report_sha256,
                    delivered.verdict,
                ),
            )

    def _save_settlement(self, request_id: str, settlement: dict[str, Any]) -> None:
        self.settlements[request_id] = settlement
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO settlements (request_id, plan_json, reference) VALUES (?, ?, ?)",
                (
                    request_id,
                    json.dumps(settlement["plan"], sort_keys=True),
                    settlement["reference"],
                ),
            )

    def _save_real_task(self, task_id: str, request_id: str, reviewer: str) -> None:
        self.real_tasks[task_id] = (request_id, reviewer)
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO review_tasks (task_id, reviewer, kind, request_id) "
                "VALUES (?, ?, 'real', ?) ON CONFLICT (task_id) DO NOTHING",
                (task_id, reviewer, request_id),
            )

    def _save_calibration_task(self, task: cal.CalibrationTask) -> None:
        self.calibration_tasks[task.task_id] = task
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO review_tasks (task_id, reviewer, kind, calibration_json) "
                "VALUES (?, ?, 'calibration', ?) ON CONFLICT (task_id) DO UPDATE SET "
                "calibration_json = excluded.calibration_json",
                (task.task_id, task.reviewer, json.dumps(task.to_document(), sort_keys=True)),
            )

    def _reload(self) -> None:
        """Rebuild the working state from storage (after a rollback or on start)."""
        if self.storage is None:  # pragma: no cover - only called when stored
            return
        db = self.storage.db
        self.files = StoredFiles(self.storage)  # type: ignore[assignment]
        self.request_documents = {
            row["request_id"]: self.storage.files.get(row["request_sha256"])
            for row in db.query("SELECT request_id, request_sha256 FROM requests")
        }
        self.records = {
            row["request_id"]: lc.record_from_document(json.loads(row["record_json"]))
            for row in db.query("SELECT request_id, record_json FROM requests ORDER BY request_id")
        }
        self.deliveries = {
            row["request_id"]: Delivered(
                row["request_id"],
                row["station"],
                row["observations_sha256"],
                row["observations_format"],
                row["report_sha256"],
                row["verdict"],
            )
            for row in db.query("SELECT * FROM deliveries ORDER BY request_id")
        }
        self.settlements = {
            row["request_id"]: {"plan": json.loads(row["plan_json"]), "reference": row["reference"]}
            for row in db.query("SELECT * FROM settlements ORDER BY request_id")
        }
        self.real_tasks = {}
        self.calibration_tasks = {}
        for row in db.query("SELECT * FROM review_tasks ORDER BY task_id"):
            if row["kind"] == "real":
                self.real_tasks[row["task_id"]] = (row["request_id"], row["reviewer"])
            else:
                task = cal.CalibrationTask.from_document(json.loads(row["calibration_json"]))
                self.calibration_tasks[task.task_id] = task
        self.element_sets = {}
        for row in db.query("SELECT * FROM element_sets ORDER BY norad_id, epoch, sha256"):
            stored = orbits.StoredSet.from_row(row)
            self.element_sets.setdefault(stored.norad_id, []).append(stored)
        self.allowlist_groups = {
            row["group_name"]: {
                "fetched_at": row["fetched_at"],
                "sha256": row["sha256"],
                "members": {int(n): name for n, name in json.loads(row["members_json"])},
            }
            for row in db.query(
                "SELECT * FROM allowlist_groups WHERE members_json IS NOT NULL ORDER BY group_name"
            )
        }
        self.allowlist_additions = {
            int(row["norad_id"]): {
                "name": row["name"],
                "reason": row["reason"],
                "added_at": row["added_at"],
                "added_by": row["added_by"],
            }
            for row in db.query("SELECT * FROM allowlist_additions ORDER BY norad_id")
        }
        self._targets = None
        reload = getattr(self.adapter, "reload", None)
        if reload is not None:
            reload()

    def refresh(self) -> None:
        """Bring the copy in memory up to date with the database, which another process may
        have changed (step 4.2). Every call does this by itself; this is for reads outside a
        call."""
        if self.storage is not None:
            with self.storage.db.transaction():
                pass

    # ------------------------------------------------------------------ helpers

    def _record(self, request_id: str) -> RequestRecord:
        try:
            return self.records[request_id]
        except KeyError:
            raise ServiceError("unknown_request", f"no request {request_id!r}") from None

    def on_chain(self, request_id: str) -> bool:
        """Whether the request was funded on chain, so that its parties sign (step 2.6)."""
        return self.chain is not None and self.chain.on_chain(request_id)

    def _off_chain(self, request_id: str) -> None:
        if self.on_chain(request_id):
            raise ServiceError(
                "sign_on_chain",
                f"request {request_id} is on chain: its parties sign their own transactions",
            )

    def _apply(self, request_id: str, event: lc.Event) -> RequestRecord:
        self._off_chain(request_id)
        try:
            record = lc.apply(self._record(request_id), event)
        except TransitionError as error:
            raise ServiceError(error.code, str(error)) from None
        self._save_record(record)
        return self._settle_if_finished(request_id, event.at)

    def _store(self, data: bytes) -> str:
        if self.storage is not None:
            return self.storage.put_file(data)
        digest = sha256_bytes(data)
        self.files.setdefault(digest, data)
        return digest

    def _settle_if_finished(self, request_id: str, now: datetime) -> RequestRecord:
        record = self.records[request_id]
        if record.status not in lc.OUTCOMES:
            return record
        plan = settlement_plan(record, platform=self.platform)
        key = f"{request_id}/settle"
        try:
            if record.status in (Status.EXPIRED, Status.CANCELLED) and plan.deposit:
                receipt = self.adapter.refund(request_id, record.requester, key=key)
            else:
                receipt = self.adapter.settle(plan, key=key)
        except SettlementError as error:  # pragma: no cover - the rules keep these consistent
            raise ServiceError(error.code, str(error)) from None
        self._save_settlement(
            request_id, {"plan": plan.to_document(), "reference": receipt.reference}
        )
        record = lc.apply(record, lc.Settle(max(now, record.updated_at)))
        return self._save_record(record)

    # ------------------------------------------------------------------ requester

    @_atomic
    def create(
        self,
        request_bytes: bytes,
        requester: str,
        now: datetime,
        *,
        replay_by: str | None = None,
        **terms: Any,
    ) -> RequestRecord:
        """Create a request in draft. A replay request (format 1.1) only an administrator
        creates, for a requester, and ``replay_by`` names the administrator (D-51)."""
        try:
            parsed_terms = lc.terms_from_request(request_bytes, requester, **terms)
        except ValueError as error:
            raise ServiceError("invalid_request", str(error)) from None
        request_id = parsed_terms.request_id
        if request_id in self.records:
            raise ServiceError("duplicate_request", f"request {request_id} already exists")
        target = self.targets().get(parsed_terms.target_norad_id)
        if target is None:
            raise ServiceError(
                "target_not_allowed",
                f"object {parsed_terms.target_norad_id} is not on the allow-list: requests may "
                "target only the civilian objects on it",
            )
        parsed = Request.parse(request_bytes)
        if target.simulated and not parsed.simulated:
            raise ServiceError(
                "simulated_target",
                f"object {target.norad_id} is SIMULATED, so a request for it must be marked as "
                "SIMULATED too",
            )
        if parsed.replay is not None:
            if replay_by is None:
                raise ServiceError(
                    "replay_admin_only", "only an administrator creates a replay request"
                )
            if parsed_terms.window_end > now:
                raise ServiceError(
                    "replay_window_not_past",
                    "a replay's window lies in the past: it replays observations already "
                    "published, and a coming pass is a normal request",
                )
            if parsed_terms.delivery_deadline <= now:
                raise ServiceError(
                    "invalid_request",
                    "a replay's delivery deadline must be in the future; give one in the terms",
                )
        elif replay_by is not None:
            raise ServiceError("not_a_replay", "the request document has no replay block")
        self.request_documents[request_id] = request_bytes
        self._store(request_bytes)
        return self._save_record(lc.create(parsed_terms, now))

    def _require_requester(self, request_id: str, party: str) -> None:
        if party != self._record(request_id).requester:
            raise ServiceError("not_requester", "only the requester can do this")

    @_atomic
    def open(self, request_id: str, party: str, now: datetime) -> RequestRecord:
        self._require_requester(request_id, party)
        return self._apply(request_id, lc.Open(now))

    @_atomic
    def fund(
        self, request_id: str, party: str, split: lc.RewardSplit, now: datetime
    ) -> RequestRecord:
        self._require_requester(request_id, party)
        if self.chain is not None:
            raise ServiceError("sign_on_chain", "on chain, the requester funds with its own wallet")
        before = self._record(request_id)
        record = self._apply(request_id, lc.Fund(now, split))
        try:
            self.adapter.fund(request_id, party, split.total, key=f"{request_id}/fund")
        except SettlementError as error:
            self._save_record(before)  # keep the lifecycle and the books in step
            raise ServiceError(error.code, str(error)) from None
        return record

    @_atomic
    def cancel(self, request_id: str, party: str, now: datetime) -> RequestRecord:
        return self._apply(request_id, lc.Cancel(now, party))

    # ------------------------------------------------------------------ station

    def replay_of(self, request_id: str) -> Replay | None:
        """The request's replay block, if it is a replay (D-51)."""
        if request_id not in self._replays:
            document = self.request_documents.get(request_id)
            if document is None:
                return None  # not known yet: nothing to remember
            self._replays[request_id] = Request.parse(document).replay
        return self._replays[request_id]

    def check_reserve(self, request_id: str, station: str) -> None:
        """Only its replay station reserves a replay; before the chain is asked, too."""
        replay = self.replay_of(request_id)
        if replay is not None and station != replay.station:
            raise ServiceError(
                "replay_station_only",
                f"{request_id} is a replay of published observations: only its replay station "
                "delivers it",
            )

    def check_delivery(self, request_id: str, station: str, observations: bytes) -> None:
        """A replay delivers exactly the file it names, and only once the service keeps a
        reference orbit for it: SatChecker's set nearest its window, which the follower
        fetches once the request is open (D-51). Before the chain is asked, too."""
        replay = self.replay_of(request_id)
        if replay is None:
            return
        self.check_reserve(request_id, station)
        if sha256_bytes(observations) != replay.observations_sha256:
            raise ServiceError(
                "not_the_replayed_file",
                f"{request_id} replays the file with SHA-256 {replay.observations_sha256}, and "
                "only that file can be delivered for it",
            )
        terms = self._record(request_id).terms
        middle = terms.window_start + (terms.window_end - terms.window_start) / 2
        limit = timedelta(days=PARAMETERS["max_reference_age_days"])
        epochs = [s.epoch_time for s in self.element_sets.get(terms.target_norad_id, [])]
        if not any(e is not None and abs(e - middle) <= limit for e in epochs):
            raise ServiceError(
                "reference_orbit_pending",
                f"the service keeps no element set of object {terms.target_norad_id} within "
                f"{PARAMETERS['max_reference_age_days']:g} days of the window yet. The follower "
                "fetches SatChecker's nearest set once the request is open; try again later",
            )

    @_atomic
    def reserve(self, request_id: str, station: str, now: datetime) -> RequestRecord:
        self.check_reserve(request_id, station)
        record = self._apply(request_id, lc.Reserve(now, station))
        count = sum(1 for h in record.history if h.event == "reserve")
        self.adapter.reserve(request_id, station, key=f"{request_id}/reserve/{count}")
        return record

    @_atomic
    def deliver(
        self,
        request_id: str,
        station: str,
        observations: bytes,
        now: datetime,
        observations_format: str | None = None,
    ) -> RequestRecord:
        """Accept a delivery and run automated verification at once."""
        self.check_delivery(request_id, station, observations)
        observations_sha256 = sha256_bytes(observations)
        self._apply(request_id, lc.Deliver(now, station, observations_sha256))
        delivered = self._verify(request_id, station, observations, observations_format)
        self.adapter.attest(
            request_id,
            VERIFIER,
            "automated_verification",
            delivered.report_sha256,
            delivered.verdict,
            key=f"{request_id}/verification",
        )
        reviewers: tuple[str, ...] = ()
        if delivered.verdict == "inconclusive":
            reviewers = self._select(request_id, observations_sha256, challenger=None)
        record = self._apply(
            request_id,
            lc.RecordVerification(now, delivered.verdict, delivered.report_sha256, reviewers),
        )
        if record.status is Status.IN_REVIEW:
            self._assign(request_id, now)
        return record

    def _verify(
        self,
        request_id: str,
        station: str,
        observations: bytes,
        observations_format: str | None,
    ) -> Delivered:
        """Keep a delivered file, run automated verification and keep its report."""
        observations_sha256 = self._store(observations)
        try:
            norad_id = Request.parse(self.request_documents[request_id]).norad_id
        except FormatError:  # pragma: no cover - a stored request was valid when it was made
            norad_id = None
        previous = sorted(
            (self.files[d.observations_sha256] for d in self.deliveries.values()),
            key=sha256_bytes,
        )
        try:
            report = verify(
                VerificationInput(
                    request=self.request_documents[request_id],
                    observations=observations,
                    observations_format=observations_format,
                    catalog=self.catalog_for([] if norad_id is None else [norad_id]),
                    policy=self.policy_for(norad_id),
                    previous=previous,
                    declared_sha256=observations_sha256,
                    sites=self.context.sites,
                )
            )
        except UsageError as error:  # a configuration problem, not the station's fault
            raise ServiceError("verification_unavailable", str(error)) from None
        report_bytes = dumps_pretty(report, sort_keys=False).encode("utf-8")
        delivered = Delivered(
            request_id,
            station,
            observations_sha256,
            observations_format,
            self._store(report_bytes),
            report["verdict"],
        )
        self._save_delivery(delivered)
        return delivered

    # ------------------------------------------------------------------ reference orbits

    def simulated_objects(self) -> set[int]:
        """The objects of the service's own catalogue when it is SIMULATED: they keep their
        own orbits, and nothing real is fetched or kept for them."""
        base = parse_catalog(self.context.catalog)
        return set(base.sets) if base.simulated else set()

    def simulation_catalog(self, norad_id: int, start: datetime, end: datetime) -> bytes:
        """The catalogue that a simulated station observes an object with (D-50). For the
        service's own objects it is the service's own catalogue, as before. For a real
        object it is the stored element set nearest the middle of the window, alone, so that
        the SIMULATED observations follow the set that verification picks for them."""
        stored = self.element_sets.get(norad_id, [])
        if not stored:
            if norad_id in parse_catalog(self.context.catalog).sets:
                return self.context.catalog
            raise ServiceError(
                "no_reference_orbit",
                f"object {norad_id} has no element set yet. The follower fetches it from "
                "CelesTrak from a day before a request's window starts; try again later",
            )
        middle = start + (end - start) / 2
        nearest = parse_catalog(self.catalog_for([norad_id])).nearest(norad_id, middle)
        if abs(nearest.epoch - middle) > timedelta(days=PARAMETERS["max_reference_age_days"]):
            raise ServiceError(
                "no_reference_orbit",
                f"object {norad_id} has no element set within "
                f"{PARAMETERS['max_reference_age_days']:g} days of the window; the nearest is "
                f"from {format_utc(nearest.epoch)}",
            )
        document = {
            "format": "orbit-watch/gp-catalog",
            "format_version": "1.0",
            "simulated": False,
            "description": (
                "A real element set that the service keeps, for SIMULATED observations of a "
                "real object. Not for redistribution."
            ),
            "records": [nearest.record],
        }
        return dumps_pretty(document, sort_keys=False).encode("utf-8")

    def catalog_for(self, norad_ids: list[int]) -> bytes:
        """The catalogue that verifies these objects (step 5.4, D-47). Without stored sets
        it is the service's own catalogue, as before. With them it holds every stored set of
        the objects, from which verification picks the one nearest the observations (P5-04),
        and the service's own records of the objects when those are real too."""
        stored = [s.record for norad in norad_ids for s in self.element_sets.get(norad, [])]
        if not stored:
            return self.context.catalog
        base = parse_catalog(self.context.catalog)
        records = list(stored)
        if not base.simulated:
            records += [r for norad in norad_ids for r in base.sets.get(norad, [])]
        document = {
            "format": "orbit-watch/gp-catalog",
            "format_version": "1.0",
            "simulated": False,
            "description": (
                "Real element sets that the service keeps: fetched from CelesTrak or "
                "SatChecker, or uploaded by an administrator. Not for redistribution."
            ),
            "records": records,
        }
        return dumps_pretty(document, sort_keys=False).encode("utf-8")

    @_atomic
    def keep_element_sets(
        self,
        records: list[dict[str, Any]],
        source: str,
        now: datetime,
        uploaded_by: str | None = None,
    ) -> tuple[list[orbits.StoredSet], int]:
        """Keep real element sets; returns the new ones and how many were already kept. A
        set of a SIMULATED object is refused: the simulated objects have their own orbits,
        and a real set of one would only confuse the labels (P5-09)."""
        simulated = self.simulated_objects()
        fetched_at = format_utc(now)
        new: list[orbits.StoredSet] = []
        already = 0
        for record in records:
            stored = orbits.keep(record, source, fetched_at, uploaded_by)
            if stored.norad_id in simulated:
                raise ServiceError(
                    "simulated_object",
                    f"object {stored.norad_id} is SIMULATED; it has no real element sets",
                )
            known = {s.sha256 for s in self.element_sets.get(stored.norad_id, [])}
            if stored.sha256 in known or any(n.sha256 == stored.sha256 for n in new):
                already += 1
                continue
            new.append(stored)
        for stored in new:
            if self.storage is not None:
                self.storage.db.execute(
                    "INSERT INTO element_sets (sha256, norad_id, epoch, source, fetched_at, "
                    "uploaded_by, record_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    stored.row(),
                )
            self.element_sets.setdefault(stored.norad_id, []).append(stored)
            self.element_sets[stored.norad_id].sort(key=lambda s: (s.epoch, s.sha256))
        if new:
            self._targets = None  # the name patterns apply to the sets' names too
        return new, already

    def reference_orbits(self, norad_id: int | None = None) -> list[dict[str, Any]]:
        """The names of the kept element sets, never their elements (P5-05)."""
        objects = [norad_id] if norad_id is not None else sorted(self.element_sets)
        return [s.public() for norad in objects for s in self.element_sets.get(norad, [])]

    # ------------------------------------------------------------------ allow-list

    def targets(self) -> dict[int, allowlist.Target]:
        """The objects requests may target, and why (D-05, P5-08, D-49): the service's own
        list, CelesTrak's civilian groups and an administrator's additions, minus the
        excluded groups and the name patterns, which apply to the names of the stored
        element sets too."""
        if self._targets is None:
            names = {
                norad: [str(s.record.get("OBJECT_NAME") or "") for s in sets]
                for norad, sets in self.element_sets.items()
            }
            self._targets = allowlist.combine(
                self.context.policy,
                {group: info["members"] for group, info in self.allowlist_groups.items()},
                self.allowlist_additions,
                names,
            )
        return self._targets

    def policy_for(self, norad_id: int | None) -> bytes:
        """The allow-list that verifies a delivery for this object. For a real object it
        holds only the real objects, so that its report does not say SIMULATED (P5-09); for
        any other object it is the service's own list, as before."""
        target = self.targets().get(norad_id) if norad_id is not None else None
        if target is None or target.source == "service":
            return self.context.policy
        built_from: list[dict[str, Any]] = [
            {
                "role": "include" if group in allowlist.INCLUDED_GROUPS else "exclude",
                "group": group,
                "source": "CelesTrak",
                "fetched_at": info["fetched_at"],
                "sha256": info["sha256"],
                "records": len(info["members"]),
            }
            for group, info in self.allowlist_groups.items()
            if group in allowlist.GROUPS
        ]
        if self.allowlist_additions:
            built_from.append({"role": "administrator", "records": len(self.allowlist_additions)})
        real = [t for t in self.targets().values() if not t.simulated]
        document = {
            "format": "orbit-watch/target-policy",
            "format_version": "1.0",
            "simulated": False,
            "description": (
                f"The service's real objects: {len(real)} from CelesTrak's groups "
                f"{', '.join(allowlist.INCLUDED_GROUPS)} and an administrator's additions, "
                f"minus the groups {', '.join(allowlist.EXCLUDED_GROUPS)} and the name "
                "patterns (decision D-49)."
            ),
            "built_from": built_from,
            "allow": [
                {"norad_id": t.norad_id, **({"name": t.name} if t.name else {})} for t in real
            ],
        }
        return dumps_pretty(document, sort_keys=False).encode("utf-8")

    @_atomic
    def keep_group(self, group: str, body: bytes, now: datetime) -> int:
        """Keep the objects of a CelesTrak group that the follower fetched; returns how many
        it holds. Its element sets are not kept: the follower fetches those of a request's
        object when it needs them."""
        if group not in allowlist.GROUPS:
            raise ServiceError("unknown_group", f"{group!r} is not one of the list's groups")
        catalog = parse_catalog(body)
        members = {norad: catalog.name(norad) for norad in sorted(catalog.records)}
        info = {"fetched_at": format_utc(now), "sha256": sha256_bytes(body), "members": members}
        if self.storage is not None:
            self.storage.db.execute(
                "UPDATE allowlist_groups SET fetched_at = ?, sha256 = ?, members_json = ? "
                "WHERE group_name = ?",
                (info["fetched_at"], info["sha256"], json.dumps(sorted(members.items())), group),
            )
        self.allowlist_groups[group] = info
        self._targets = None
        return len(members)

    @_atomic
    def allow_object(
        self, norad_id: int, name: str, reason: str, by: str, now: datetime
    ) -> allowlist.Target:
        """An administrator adds a real object to the list, after checking its owner in the
        satellite catalogue; the reason is public (P5-08). The name patterns and the
        excluded groups still apply."""
        name, reason = name.strip(), reason.strip()
        if not name or len(name) > 200:
            raise ServiceError("invalid_name", "the name must have 1 to 200 characters")
        if not reason or len(reason) > 500:
            raise ServiceError("invalid_reason", "the reason must have 1 to 500 characters")
        target = self.targets().get(norad_id)
        if target is not None and target.source == "service":
            raise ServiceError("already_allowed", f"object {norad_id} is on the service's own list")
        if norad_id in self.simulated_objects():
            raise ServiceError("simulated_object", f"object {norad_id} is SIMULATED")
        names = [name] + [
            str(s.record.get("OBJECT_NAME") or "") for s in self.element_sets.get(norad_id, [])
        ]
        if any(allowlist.excluded_name(n) for n in names):
            raise ServiceError(
                "excluded_name",
                f"the name of object {norad_id} matches the patterns for military, intelligence "
                "and government security payloads",
            )
        for group in allowlist.EXCLUDED_GROUPS:
            if norad_id in self.allowlist_groups.get(group, {}).get("members", {}):
                raise ServiceError(
                    "excluded_group", f"object {norad_id} is in CelesTrak's group {group}"
                )
        added = {"name": name, "reason": reason, "added_at": format_utc(now), "added_by": by}
        if self.storage is not None:
            self.storage.db.execute(
                "INSERT INTO allowlist_additions (norad_id, name, reason, added_at, added_by) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT (norad_id) DO UPDATE SET name = "
                "excluded.name, reason = excluded.reason, added_at = excluded.added_at, "
                "added_by = excluded.added_by",
                (norad_id, name, reason, added["added_at"], by),
            )
        self.allowlist_additions[norad_id] = added
        self._targets = None
        return self.targets()[norad_id]

    @_atomic
    def disallow_object(self, norad_id: int) -> None:
        """An administrator takes back an addition. An object of the groups stays."""
        if norad_id not in self.allowlist_additions:
            raise ServiceError("unknown_target", f"object {norad_id} is not an addition")
        if self.storage is not None:
            self.storage.db.execute(
                "DELETE FROM allowlist_additions WHERE norad_id = ?", (norad_id,)
            )
        del self.allowlist_additions[norad_id]
        self._targets = None

    # ------------------------------------------------------------------ challenges

    def _select(
        self, request_id: str, delivery_sha256: str, challenger: str | None
    ) -> tuple[str, ...]:
        record = self._record(request_id)
        parties = {record.requester, record.observer or "", challenger or ""}
        try:
            return self.reviewers.select(request_id, delivery_sha256, parties)
        except ReviewerError as error:
            raise ServiceError(error.code, str(error)) from None

    @_atomic
    def challenge(self, request_id: str, party: str, reason: str, now: datetime) -> RequestRecord:
        if not reason.strip():
            raise ServiceError("reason_required", "a challenge must say why")
        self._off_chain(request_id)
        record = lc.advance(self._record(request_id), now)
        if record.status is not Status.CHALLENGE_PERIOD:
            raise ServiceError(
                "forbidden_in_status",
                f"'challenge' is not allowed when the request is {record.status}",
            )
        self._save_record(record)
        reviewers = self._select(request_id, record.delivery_sha256 or "", challenger=party)
        record = self._apply(request_id, lc.Challenge(now, party, reviewers, reason))
        self._assign(request_id, now)
        return record

    @_atomic
    def vote(
        self, request_id: str, reviewer: str, approve: bool, reason: str, now: datetime
    ) -> RequestRecord:
        if not reason.strip():
            raise ServiceError("reason_required", "a review must give its reasons")
        record = self._apply(request_id, lc.Vote(now, reviewer, approve, reason))
        delivered = self.deliveries[request_id]
        self.adapter.attest(
            request_id,
            reviewer,
            "review_vote",
            delivered.observations_sha256,
            "approve" if approve else "reject",
            key=f"{request_id}/vote/{reviewer}",
        )
        return record

    # ------------------------------------------------------------------ reviewer tasks

    def _task_id(self, *parts: str) -> str:
        return "task-" + sha256_bytes("|".join((self.task_salt, *parts)).encode())[:20]

    def _assign(self, request_id: str, now: datetime) -> None:
        """Give each reviewer of the round its real task and its calibration tasks."""
        record = self._record(request_id)
        due = record.review_deadline or now
        for reviewer in record.reviewers:
            self._save_real_task(self._task_id("real", request_id, reviewer), request_id, reviewer)
            for number in range(self.calibration_per_assignment):
                source = f"{request_id}|{reviewer}|{number}"
                history = [t for t in self.calibration_tasks.values() if t.reviewer == reviewer]
                kind = cal.choose_kind(reviewer, history, source)
                request_bytes, observations, report, verdict = cal.build_files(kind, source)
                task = cal.CalibrationTask(
                    task_id=self._task_id("calibration", source),
                    reviewer=reviewer,
                    kind=kind,
                    expected=cal.KINDS[kind],
                    request_sha256=self._store(request_bytes),
                    observations_sha256=self._store(observations),
                    report_sha256=self._store(report),
                    automated_verdict=verdict,
                    challenge_reason=cal.challenge_text(kind, source),
                    created_at=now,
                    due_at=due,
                )
                self._save_calibration_task(task)

    def assignments(self, reviewer: str, now: datetime) -> list[dict[str, Any]]:
        """Open review tasks of a reviewer, real and calibration alike, in one shape."""
        open_tasks = []
        for task_id, (request_id, assigned) in self.real_tasks.items():
            record = lc.advance(self._record(request_id), now)
            voted = any(r == assigned for r, _ in record.votes)
            if assigned != reviewer or record.status is not Status.IN_REVIEW or voted:
                continue
            delivered = self.deliveries[request_id]
            open_tasks.append(
                {
                    "task_id": task_id,
                    "request_sha256": sha256_bytes(self.request_documents[request_id]),
                    "observations_sha256": delivered.observations_sha256,
                    "report_sha256": delivered.report_sha256,
                    "automated_verdict": delivered.verdict,
                    "challenge_reason": record.challenge_reason
                    or "The automated result was inconclusive.",
                    "due": format_utc(record.review_deadline),
                }
            )
        for task in self.calibration_tasks.values():
            if task.reviewer != reviewer or task.answer is not None or task.due_at <= now:
                continue
            open_tasks.append(
                {
                    "task_id": task.task_id,
                    "request_sha256": task.request_sha256,
                    "observations_sha256": task.observations_sha256,
                    "report_sha256": task.report_sha256,
                    "automated_verdict": task.automated_verdict,
                    "challenge_reason": task.challenge_reason,
                    "due": format_utc(task.due_at),
                }
            )
        return sorted(open_tasks, key=lambda t: t["task_id"])

    @_atomic
    def review(
        self, task_id: str, reviewer: str, approve: bool, reason: str, now: datetime
    ) -> dict[str, Any]:
        """Answer a review task. The answer never says whether the task was real."""
        if not reason.strip():
            raise ServiceError("reason_required", "a review must give its reasons")
        if task_id in self.real_tasks:
            request_id, assigned = self.real_tasks[task_id]
            if assigned != reviewer:
                raise ServiceError("not_your_task", "this task belongs to another reviewer")
            self.vote(request_id, reviewer, approve, reason, now)
            return {"task_id": task_id, "recorded": True}
        task = self.calibration_tasks.get(task_id)
        if task is None:
            raise ServiceError("unknown_task", f"no task {task_id!r}")
        if task.reviewer != reviewer:
            raise ServiceError("not_your_task", "this task belongs to another reviewer")
        if task.answer is not None:
            raise ServiceError("already_voted", f"{reviewer} has already voted")
        if now >= task.due_at:
            raise ServiceError("forbidden_in_status", "the review deadline has passed")
        task.answer = "approve" if approve else "reject"
        task.reason = reason
        task.answered_at = now
        self._save_calibration_task(task)
        return {"task_id": task_id, "recorded": True}

    def reviewer_profile(self, reviewer: str, now: datetime) -> dict[str, Any]:
        """Accuracy on calibration tasks and voting behaviour in real rounds."""
        votes = []
        for request_id in sorted(self.records):
            record = self.records[request_id]
            for voter, approve in record.votes:
                if voter == reviewer:
                    outcome = None if record.outcome is None else str(record.outcome)
                    votes.append((approve, outcome))
        return cal.profile(reviewer, list(self.calibration_tasks.values()), votes, now)

    # ------------------------------------------------------------------ time

    @_atomic
    def tick(self, now: datetime) -> list[str]:
        """Apply passed deadlines to every request and settle finished ones. On a chain,
        funded requests are left to the chain (``ChainLink.follow_up``)."""
        changed = []
        for request_id in sorted(self.records):
            before = self.records[request_id]
            if before.status is Status.SETTLED or self.on_chain(request_id):
                continue
            self._save_record(lc.advance(before, now))
            after = self._settle_if_finished(request_id, now)
            if after != before:
                changed.append(request_id)
        return changed

    # ------------------------------------------------------------------ reading

    def report(self, request_id: str) -> bytes:
        try:
            return self.files[self.deliveries[request_id].report_sha256]
        except KeyError:
            raise ServiceError("no_report", f"request {request_id} has no report yet") from None

    # ------------------------------------------------------------------ publication (1.8)

    def request_files(self, request_id: str) -> list[tuple[str, str]]:
        """(role, SHA-256) of the files that belong to a request."""
        files = [("request", sha256_bytes(self.request_documents[request_id]))]
        delivered = self.deliveries.get(request_id)
        if delivered is not None:
            files += [
                ("observations", delivered.observations_sha256),
                ("report", delivered.report_sha256),
            ]
        return files

    def publication(self, request_id: str, now: datetime) -> dict[str, Any]:
        """When and under which licence a request's files are public.

        Files become public once the request is settled and its embargo (0 to 30
        days, fixed in the terms) has passed. Until then only the parties of the
        request and administrators can read them.
        """
        record = self._record(request_id)
        terms = record.terms
        settled = next((h.at for h in reversed(record.history) if h.event == "settle"), None)
        public_from = None if settled is None else settled + timedelta(days=terms.embargo_days)
        if public_from is None:
            state = "pending"
        elif now >= public_from:
            state = "published"
        else:
            state = "embargoed"
        observer = record.observer
        attribution = (
            f"Observations by {observer} for {record.requester}, request {request_id}, "
            "published through Orbit Watch"
            if observer
            else f"Request {request_id} by {record.requester}, published through Orbit Watch"
        )
        return {
            "request_id": request_id,
            "state": state,
            "licence": terms.licence,
            "licence_url": LICENCE_URLS.get(terms.licence),
            "embargo_days": terms.embargo_days,
            "public_from": None if public_from is None else format_utc(public_from),
            "attribution": attribution,
            "files": [
                {
                    "role": role,
                    "sha256": digest,
                    "size": len(self.files[digest]),
                    "url": f"/v1/public/files/{digest}",
                }
                for role, digest in self.request_files(request_id)
            ],
            "simulated": bool(json.loads(self.request_documents[request_id]).get("simulated")),
        }

    def open_requests(self) -> list[dict[str, Any]]:
        """Requests that invite observers: opened or funded, not reserved (decision D-26).
        Their request documents, terms and rewards are public; anything delivered follows
        the publication rules."""
        found = []
        for request_id in sorted(self.records):
            record = self.records[request_id]
            if record.status not in (Status.OPEN, Status.FUNDED):
                continue
            terms = record.terms
            document = json.loads(self.request_documents[request_id])
            found.append(
                {
                    "request_id": request_id,
                    "status": str(record.status),
                    "requester": record.requester,
                    "request": document,
                    "request_sha256": terms.request_sha256,
                    "terms": {
                        "target_norad_id": terms.target_norad_id,
                        "window_start": format_utc(terms.window_start),
                        "window_end": format_utc(terms.window_end),
                        "delivery_deadline": format_utc(terms.delivery_deadline),
                        "reservation_hours": terms.reservation_hours,
                        "challenge_period_hours": terms.challenge_period_hours,
                        "review_hours": terms.review_hours,
                        "embargo_days": terms.embargo_days,
                        "licence": terms.licence,
                        "verification_method": terms.verification_method,
                    },
                    "split": None
                    if record.split is None
                    else {
                        "observer": record.split.observer,
                        "reviewer": record.split.reviewer,
                        "platform_fee": record.split.platform_fee,
                    },
                    "simulated": bool(document.get("simulated")),
                }
            )
        return found

    def published(self, now: datetime) -> list[dict[str, Any]]:
        return [
            self.publication(rid, now)
            for rid in sorted(self.records)
            if self.publication(rid, now)["state"] == "published"
        ]

    def parties(self, request_id: str) -> set[str]:
        record = self._record(request_id)
        return {p for p in (record.requester, record.observer, *record.reviewers) if p}

    def can_read_request_data(self, request_id: str, party: str, role: str, now: datetime) -> bool:
        return (
            role == "admin"
            or party in self.parties(request_id)
            or self.publication(request_id, now)["state"] == "published"
        )

    def can_read_file(
        self, sha256: str, party: str | None, role: str | None, now: datetime
    ) -> bool:
        """Who may download a stored file. Calibration files are never public."""
        if role == "admin":
            return sha256 in self.files
        for request_id in sorted(self.records):
            roles = {role for role, digest in self.request_files(request_id) if digest == sha256}
            if roles:
                if self.publication(request_id, now)["state"] == "published":
                    return True
                if party is not None and party in self.parties(request_id):
                    return True
                # The request document invites observers while the request is open (D-26),
                # and the station that reserved it needs it to observe (step 3.5).
                record = self.records[request_id]
                if (
                    "request" in roles
                    and party is not None
                    and (
                        record.status in (Status.OPEN, Status.FUNDED) or party == record.reserved_by
                    )
                ):
                    return True
        return any(
            task.reviewer == party
            and sha256 in (task.request_sha256, task.observations_sha256, task.report_sha256)
            for task in self.calibration_tasks.values()
        )

    def summary(self, request_id: str) -> dict[str, Any]:
        record = self._record(request_id)
        delivered = self.deliveries.get(request_id)
        return {
            "request_id": request_id,
            "status": str(record.status),
            "outcome": None if record.outcome is None else str(record.outcome),
            "outcome_reason": record.outcome_reason,
            "automated_verdict": None if delivered is None else delivered.verdict,
            "reviewers": list(record.reviewers),
            "votes": [[r, a] for r, a in record.votes],
            "settlement": self.settlements.get(request_id),
        }


def open_service(
    database: str,
    reviewers: ReviewerRegistry,
    context: VerificationContext,
    *,
    chain: Any = None,
    database_role: str | None = None,
    **options: Any,
) -> RequestService:
    """A service whose state, files included, lives in the PostgreSQL ``database`` (a libpq
    connection string or URL) and survives restarts (decision P4-04).

    Any number of processes can open the same schema; each reloads its copy of the state
    when another one changed it (step 4.2). With ``chain`` (an ``orbit_watch.chain.link.ChainLink``)
    the service works on that testnet chain (step 2.6). With ``database_role``, the
    database's own user runs the migrations, and every transaction runs as that role, which
    may only read and write the service's tables (step 4.5, decision P4-10).
    """
    from orbit_watch.settlement.stored_ledger import StoredLedgerAdapter

    storage = Storage(database, role=database_role)
    try:
        service = RequestService(
            StoredLedgerAdapter(storage.db), reviewers, context, storage=storage, **options
        )
        # The copy and the version it matches, read together under the lock.
        with storage.db.transaction():
            service._reload()
            storage.db.version_seen = storage.db.current_version()
    except BaseException:
        storage.close()
        raise

    def refresh(db: Any) -> None:
        """Another process changed the state, or a transaction of this one was rolled back:
        reload the copy in memory (decision P4-06)."""
        version = db.current_version()
        if version != db.version_seen:
            service._reload()
            db.version_seen = version

    storage.db.add_begin_hook(refresh)
    if chain is not None:
        try:
            chain.attach(service)
        except BaseException:
            storage.close()
            raise
        service.chain = chain
    return service
