"""A request service on a local Anvil chain, for the step 2.6 tests.

Everything here is LOCAL and SIMULATED: the chain is a throw-away Anvil process, the token
is the worthless TestUSD, and every party's account is a local test account derived from
its name (tests/anvil.py). Each party signs with its own account through
``orbit_watch.chain.wallet``, the way the command line does; the service holds only the
verifier key.
"""

from __future__ import annotations

from pathlib import Path

from anvil import Deployment
from helpers import catalog_bytes, packaged, policy_bytes

from orbit_watch.chain.client import OrbitWatchChain
from orbit_watch.chain.link import ChainLink
from orbit_watch.chain.wallet import Wallet
from orbit_watch.reviewers import ReviewerRegistry
from orbit_watch.service import VerificationContext, open_service
from orbit_watch.timeutil import parse_utc

GENESIS = int(parse_utc("2026-11-01T12:00:00Z").timestamp())
REQUESTER = "requester:sim-cubesat-team"
STATION = "station:SIM-ESPOO"
STRANGER = "station:sim-stranger"
PLATFORM = "platform:orbit-watch"
VERIFIER = "system:verifier"
REGISTRY = ReviewerRegistry.parse(packaged("reviewers.json"))
REVIEWERS = [reviewer.id for reviewer in REGISTRY.reviewers]
BUDGET = 1_000_000_000  # 1000 TestUSD (6 decimals), worthless


class ChainWorld:
    """A fresh chain with the contracts, and a stored service that follows it. With
    ``governance``, a timelock owns the reviewer registry and a Safe proposes to it, as on
    Base Sepolia (step 3.7)."""

    def __init__(self, directory: Path, *, governance: bool = False, parties: tuple = ()):
        self.deployment = Deployment(
            GENESIS,
            reviewers=REVIEWERS,
            platform=PLATFORM,
            verifier=VERIFIER,
            parties=[REQUESTER, STATION, STRANGER, PLATFORM, *REVIEWERS, *parties],
            governance=governance,
        )
        self.local = self.deployment.chain
        self.w3 = self.local.w3
        self.directory = directory
        deployer = self.deployment.deployer
        usd = self.deployment.usd
        self.local.send(deployer, usd.functions.mint(self.address(REQUESTER), BUDGET))
        self.service = self.open()

    def open(self, escrow: str | None = None):
        chain = OrbitWatchChain(self.w3, escrow or self.deployment.escrow.address)
        safe = self.deployment.safe
        link = ChainLink(
            chain,
            self.deployment.accounts[VERIFIER],
            receipt_timeout=30,
            safe=None if safe is None else safe.address,
        )
        context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
        return open_service(self.directory, REGISTRY, context, chain=link)

    @property
    def link(self) -> ChainLink:
        return self.service.chain

    @property
    def chain(self) -> OrbitWatchChain:
        return self.link.chain

    def account(self, party: str):
        return self.deployment.accounts[party]

    def address(self, party: str) -> str:
        return self.account(party).address

    def wallet(self, party: str) -> Wallet:
        return Wallet(self.w3, self.account(party), timeout=30)

    def travel(self, when: str) -> None:
        """Move the chain's clock to ``when`` (UTC); the next block is mined then."""
        self.chain.travel_to(int(parse_utc(when).timestamp()))

    def stop(self) -> None:
        self.service.storage.close()
        self.local.stop()
