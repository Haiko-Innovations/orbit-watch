"""The points ledger, persisted in SQLite (phase 1, step 1.5).

Same rules and same behaviour as ``LedgerAdapter``; every journal entry, every
settled request and every attestation is also written to the database inside
the caller's transaction. On start the ledger is rebuilt from the journal, and
the rebuilt journal must balance.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from orbit_watch.lifecycle import RequestRecord
from orbit_watch.settlement import Receipt, SettlementPlan
from orbit_watch.settlement.ledger import JournalEntry, LedgerAdapter, Posting
from orbit_watch.storage import Database, StorageError


class SqliteLedgerAdapter(LedgerAdapter):
    name = "ledger"

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self.reload()

    def reload(self) -> None:
        """Rebuild the in-memory state from the database."""
        self.journal = []
        self._balances = defaultdict(int)
        self._by_key = {}
        self._settled = {}
        self.attestations = []
        postings: dict[int, list[Posting]] = defaultdict(list)
        for row in self.db.query(
            "SELECT seq, account, amount FROM ledger_postings ORDER BY seq, position"
        ):
            postings[row["seq"]].append(Posting(row["account"], row["amount"]))
        for row in self.db.query("SELECT * FROM ledger_entries ORDER BY seq"):
            entry = JournalEntry(
                row["seq"],
                row["idempotency_key"],
                row["operation"],
                row["request_id"],
                tuple(postings[row["seq"]]),
                row["memo"],
            )
            if entry.seq != len(self.journal) + 1 or sum(p.amount for p in entry.postings):
                raise StorageError("broken_journal", f"journal entry {entry.seq} is inconsistent")
            self.journal.append(entry)
            for posting in entry.postings:
                self._balances[posting.account] += posting.amount
            receipt = Receipt(
                entry.key,
                entry.operation,
                entry.request_id,
                f"ledger:{entry.seq}",
                tuple((p.account, p.amount) for p in entry.postings),
            )
            self._by_key[entry.key] = (row["fingerprint"], receipt)
        for row in self.db.query("SELECT request_id, idempotency_key FROM ledger_settled"):
            self._settled[row["request_id"]] = row["idempotency_key"]
        for row in self.db.query("SELECT * FROM attestations ORDER BY seq"):
            self.attestations.append(
                {
                    "request_id": row["request_id"],
                    "attester": row["attester"],
                    "kind": row["kind"],
                    "subject_sha256": row["subject_sha256"],
                    "value": row["value"],
                    "reference": f"ledger:{row['seq']}",
                }
            )

    def _guarded(self, call):
        """Run a write in a transaction; on any failure, rebuild from the database."""
        try:
            with self.db.transaction():
                return call()
        except BaseException:
            self.reload()
            raise

    def _record(
        self,
        key: str,
        fingerprint: dict[str, Any],
        operation: str,
        request_id: str | None,
        postings: list[Posting],
        memo: str,
    ) -> Receipt:
        receipt = super()._record(key, fingerprint, operation, request_id, postings, memo)
        entry = self.journal[-1]
        self.db.execute(
            "INSERT INTO ledger_entries (seq, idempotency_key, fingerprint, operation, "
            "request_id, memo) VALUES (?, ?, ?, ?, ?, ?)",
            (entry.seq, key, self._by_key[key][0], operation, request_id, memo),
        )
        for position, posting in enumerate(entry.postings):
            self.db.execute(
                "INSERT INTO ledger_postings (seq, position, account, amount) VALUES (?, ?, ?, ?)",
                (entry.seq, position, posting.account, posting.amount),
            )
        return receipt

    def grant(self, party: str, points: int, *, key: str) -> Receipt:
        return self._guarded(lambda: super(SqliteLedgerAdapter, self).grant(party, points, key=key))

    def fund(
        self,
        request_id: str,
        requester: str,
        points: int,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        return self._guarded(
            lambda: super(SqliteLedgerAdapter, self).fund(request_id, requester, points, key=key)
        )

    def reserve(
        self, request_id: str, station: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        return self._guarded(
            lambda: super(SqliteLedgerAdapter, self).reserve(request_id, station, key=key)
        )

    def attest(
        self,
        request_id: str,
        attester: str,
        kind: str,
        subject_sha256: str,
        value: str,
        *,
        key: str,
        record: RequestRecord | None = None,
    ) -> Receipt:
        def call() -> Receipt:
            before = len(self.attestations)
            receipt = super(SqliteLedgerAdapter, self).attest(
                request_id, attester, kind, subject_sha256, value, key=key
            )
            if len(self.attestations) > before:
                seq = int(receipt.reference.split(":")[1])
                self.db.execute(
                    "INSERT INTO attestations (seq, request_id, attester, kind, subject_sha256, "
                    "value) VALUES (?, ?, ?, ?, ?, ?)",
                    (seq, request_id, attester, kind, subject_sha256, value),
                )
            return receipt

        return self._guarded(call)

    def _mark_settled(self, request_id: str) -> None:
        key = self._settled.get(request_id)
        if key is not None:
            self.db.execute(
                "INSERT INTO ledger_settled (request_id, idempotency_key) VALUES (?, ?) "
                "ON CONFLICT (request_id) DO NOTHING",
                (request_id, key),
            )

    def settle(
        self, plan: SettlementPlan, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        def call() -> Receipt:
            receipt = super(SqliteLedgerAdapter, self).settle(plan, key=key)
            self._mark_settled(plan.request_id)
            return receipt

        return self._guarded(call)

    def refund(
        self, request_id: str, requester: str, *, key: str, record: RequestRecord | None = None
    ) -> Receipt:
        def call() -> Receipt:
            receipt = super(SqliteLedgerAdapter, self).refund(request_id, requester, key=key)
            self._mark_settled(request_id)
            return receipt

        return self._guarded(call)
