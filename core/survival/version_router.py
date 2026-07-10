"""Version Router — N-1 兼容 (灰犀牛 #7 版本泥潭, Function Spec §1.3).

消息头强制携带 version 字段; 平台侧实现 Version Router:
vLatest ↔ vLegacy 自动转换; 承诺 N-1 版本兼容 (v5.0 兼容 v4.x).

This bridges the v5.0 core messages to the existing v4.1 VDA5050 fabric
(MQTT/Node-RED/sap-bridge) so the new core can be rolled in alongside
the old platform without a flag-day cutover.
"""
from __future__ import annotations

from dataclasses import dataclass

from core.config import CoreConfig


@dataclass
class VersionedMessage:
    version: str
    body: dict


class VersionRouter:
    """Translate messages across supported versions."""

    def __init__(self, config: CoreConfig | None = None) -> None:
        self.cfg = config or CoreConfig()
        self.latest = self.cfg.supported_versions[0]

    def is_supported(self, version: str) -> bool:
        return version in self.cfg.supported_versions

    def normalise(self, msg: VersionedMessage) -> VersionedMessage:
        """Bring any supported version up to ``latest``."""
        if not self.is_supported(msg.version):
            raise ValueError(
                f"unsupported version {msg.version}; supported={self.cfg.supported_versions}"
            )
        if msg.version == self.latest:
            return msg
        body = self._upgrade(msg.version, self.latest, msg.body)
        return VersionedMessage(version=self.latest, body=body)

    def downgrade(self, msg: VersionedMessage, target: str) -> VersionedMessage:
        """Project a latest message back to a legacy version for old adapters."""
        if target not in self.cfg.supported_versions:
            raise ValueError(f"unsupported target version {target}")
        if msg.version == target:
            return msg
        body = self._downgrade(msg.version, target, msg.body)
        return VersionedMessage(version=target, body=body)

    # ── translation tables ─────────────────────────────────────
    # v4.x used VDA5050 field names; v5.0 uses the Function Spec names.
    _V4_TO_V5 = {
        "robotId": "robot_id",
        "bootId": "boot_id",
        "batteryLevel": "battery_percent",
        "agvPosition": "pose",
    }
    _V5_TO_V4 = {v: k for k, v in _V4_TO_V5.items()}

    def _upgrade(self, _from: str, _to: str, body: dict) -> dict:
        out = dict(body)
        for old, new in self._V4_TO_V5.items():
            if old in out:
                out[new] = out.pop(old)
        return out

    def _downgrade(self, _from: str, _to: str, body: dict) -> dict:
        out = dict(body)
        for new, old in self._V5_TO_V4.items():
            if new in out:
                out[old] = out.pop(new)
        return out
