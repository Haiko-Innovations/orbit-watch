"""Pre-approved reviewers and how a reviewer round is chosen (phase 1, step 1.3).

Reviewers are pre-approved by the maintainers and listed in a registry. Each
reviewer can declare affiliations: parties (for example their own stations or
an organisation they work for) whose requests and deliveries they must never
review. In the prototype this is how "no party reviews its own delivery" is
enforced; in phase 2 the registry is managed through a multisig with a public
timelock.

Nobody chooses the reviewers of a round, not even the challenger. They are the
three eligible reviewers with the lowest score

    SHA-256("orbit-watch-reviewers/1|" + request id + "|" + delivery SHA-256
            + "|" + round + "|" + reviewer id)

so the choice is fixed by the delivery itself, spread evenly over the
registry, and anyone can recompute it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from orbit_watch.formats.owjson import FormatError
from orbit_watch.lifecycle import REVIEWERS_PER_ROUND
from orbit_watch.schema import validate

SELECTION_VERSION = "1"


class ReviewerError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Reviewer:
    id: str
    name: str | None = None
    affiliations: frozenset[str] = field(default_factory=frozenset)


def selection_score(
    request_id: str, delivery_sha256: str, round_number: int, reviewer_id: str
) -> str:
    text = (
        f"orbit-watch-reviewers/{SELECTION_VERSION}|{request_id}|{delivery_sha256}|"
        f"{round_number}|{reviewer_id}"
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ReviewerRegistry:
    def __init__(self, reviewers: list[Reviewer], simulated: bool = False):
        ids = [r.id for r in reviewers]
        if len(ids) != len(set(ids)):
            raise ReviewerError("duplicate_reviewer", "a reviewer is listed twice")
        self.reviewers = sorted(reviewers, key=lambda r: r.id)
        self.simulated = simulated

    @classmethod
    def parse(cls, data: bytes) -> ReviewerRegistry:
        document = json.loads(data.decode("utf-8"))
        problems = validate(document, "reviewer-registry")
        if problems:
            raise FormatError("invalid reviewer registry", problems)
        return cls(
            [
                Reviewer(r["id"], r.get("name"), frozenset(r.get("affiliations", [])))
                for r in document["reviewers"]
            ],
            simulated=bool(document.get("simulated", False)),
        )

    def __contains__(self, reviewer_id: str) -> bool:
        return any(r.id == reviewer_id for r in self.reviewers)

    def eligible(self, parties: set[str]) -> list[Reviewer]:
        """Reviewers who are none of the parties and not affiliated with any of them."""
        return [r for r in self.reviewers if r.id not in parties and not (r.affiliations & parties)]

    def select(
        self, request_id: str, delivery_sha256: str, parties: set[str], round_number: int = 1
    ) -> tuple[str, ...]:
        eligible = self.eligible({p for p in parties if p})
        if len(eligible) < REVIEWERS_PER_ROUND:
            raise ReviewerError(
                "not_enough_reviewers",
                f"only {len(eligible)} independent reviewer(s) are available; a round needs "
                f"{REVIEWERS_PER_ROUND}",
            )
        ranked = sorted(
            eligible, key=lambda r: selection_score(request_id, delivery_sha256, round_number, r.id)
        )
        return tuple(r.id for r in ranked[:REVIEWERS_PER_ROUND])

    def to_document(self) -> dict[str, Any]:
        return {
            "format": "orbit-watch/reviewer-registry",
            "format_version": "1.0",
            "simulated": self.simulated,
            "reviewers": [
                {
                    "id": r.id,
                    **({"name": r.name} if r.name else {}),
                    "affiliations": sorted(r.affiliations),
                }
                for r in self.reviewers
            ],
        }
