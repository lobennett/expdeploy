"""BatteryOrchestrator — ties manifest + strategy + session."""

from __future__ import annotations

import hashlib
import json

from expdeploy.battery.counterbalance import CounterbalanceStrategy
from expdeploy.manifest import BatteryExperimentRef, BatteryManifest
from expdeploy.session import RunSession


class BatteryOrchestrator:
    def __init__(
        self,
        *,
        manifest: BatteryManifest,
        strategy: CounterbalanceStrategy,
        session: RunSession,
    ) -> None:
        self.manifest = manifest
        self.strategy = strategy
        self.session = session

    @property
    def battery_id(self) -> str:
        """Stable id derived from the manifest. Subject-independent."""
        payload = self.manifest.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return digest[:16]

    def start(self) -> None:
        experiments_by_id = {e.exp_id: e for e in self.manifest.experiments}
        order = self.strategy.order_for(self.session.subject_id, list(experiments_by_id.keys()))
        self.session.initialize(battery_id=self.battery_id, order=order)

    def next_experiment(self) -> BatteryExperimentRef | None:
        current_id = self.session.current()
        if current_id is None:
            return None
        for e in self.manifest.experiments:
            if e.exp_id == current_id:
                return e
        msg = f"current experiment {current_id!r} not in manifest"
        raise LookupError(msg)

    def advance(self) -> None:
        self.session.advance()
