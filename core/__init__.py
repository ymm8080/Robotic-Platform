"""
异构机器人融合平台 v5.0 — 核心调度平台 (Core Platform)

This package implements the v5.0 architecture described in
``Reference/Design - Core/异构机器人融合平台_v5.0_完整堡垒版.md``. It is the
Open-RMF-style scheduling/governance/survival core that sits *above* the
existing v4.1 VDA5050 adapter fabric (MQTT / Node-RED / sap-bridge).

Layer map (whitepaper §1):

    coordinator.py  平台整合层 — one map, one order queue, one platform loop
    governance/     治理层   — reputation engine, economic model (零信任博弈)
    scheduling/     核心调度层 — Task Allocator, Traffic Light, Facility Manager
    platform/       平台服务层 — Fixed Lane Map, Robot-as-Obstacle, Failover,
                                Charger Reservation, Lift Manager
    adapter/        适配层   — Fleet Adapter + Map Transformer (per-brand bridge)
    survival/       生存层   — WORM blackbox, Version Router (因果存证)
    safety/         安全距离 — dynamic formula + 1.5m legal hard floor
    messages/       接口定义 — FleetState / TaskAssignment / TrafficLightState

The scheduling patterns (Task Allocator / Traffic Light Controller /
Facility Manager) follow Open-RMF (https://github.com/open-rmf/rmf) concepts,
adapted to the fixed-lane + signal-light "降维打击" strategy of v5.0.
"""

from __future__ import annotations

__version__ = "5.0.0"
