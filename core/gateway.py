"""Transport gateway abstraction — inbound/outbound plumbing.

The coordinator is intentionally transport-agnostic. This module defines the
interface that HTTP, MQTT, DDS, or ROS2 adapters must implement to feed the
coordinator and emit commands.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

from core.adapter.fleet_adapter import AdapterCommand
from core.messages import TaskAssignment


@dataclass
class InboundMessage:
    brand: str
    raw: dict
    received_at: float


@dataclass
class OutboundEnvelope:
    robot_id: str
    brand: str
    assignment: TaskAssignment | None = None
    command: AdapterCommand | None = None


class InboundGateway(ABC):
    """Receives vendor-native robot state and forwards it to the coordinator."""

    @abstractmethod
    def start(self, callback: Callable[[InboundMessage], None]) -> None:
        """Begin receiving messages; invoke ``callback`` for each message."""

    @abstractmethod
    def stop(self) -> None:
        """Stop receiving messages."""


class OutboundGateway(ABC):
    """Sends assignments and fallback commands back to vendor fleets."""

    @abstractmethod
    def send(self, envelope: OutboundEnvelope) -> None:
        """Deliver one assignment or command to the target robot/brand."""


class MemoryGateway(InboundGateway, OutboundGateway):
    """In-memory gateway for unit tests and offline simulation."""

    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []
        self.outbound: list[OutboundEnvelope] = []
        self._callback: Callable[[InboundMessage], None] | None = None

    def inject(self, msg: InboundMessage) -> None:
        self.inbound.append(msg)
        if self._callback is not None:
            self._callback(msg)

    def start(self, callback: Callable[[InboundMessage], None]) -> None:
        self._callback = callback

    def stop(self) -> None:
        self._callback = None

    def send(self, envelope: OutboundEnvelope) -> None:
        self.outbound.append(envelope)
