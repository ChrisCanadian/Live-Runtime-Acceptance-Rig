"""Generic acceptance-contract wrapper for the Nexus monster runtime adapter.

The monster adapter exposes Nexus-native readiness as ``ready_for_test``. The
portable acceptance rig expects the generic key ``ready``. Keep both so Nexus
semantics remain visible while the reusable runner can make its normal preflight
decision.
"""

from __future__ import annotations

from typing import Any, Mapping

from live_runtime_rig.config import RigConfig
from live_runtime_rig_nexus_monster.runtime_adapter import KernelizedMonsterRuntimeAdapter


class ContractCompatibleMonsterRuntimeAdapter(KernelizedMonsterRuntimeAdapter):
    def health(self) -> Mapping[str, Any]:
        health = dict(super().health())
        health["ready"] = bool(health.get("ready_for_test"))
        return health

    def direct_readiness_probe(self) -> Mapping[str, Any]:
        return dict(self.health())


def create_runtime_adapter(config: RigConfig) -> ContractCompatibleMonsterRuntimeAdapter:
    return ContractCompatibleMonsterRuntimeAdapter(config)
