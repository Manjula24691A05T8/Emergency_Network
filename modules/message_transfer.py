from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

import networkx as nx

from modules.packet_simulation import create_transmission_plan


PRIORITIES = ("Critical", "High", "Medium", "Normal")
_PRIORITY_RANK = {priority: rank for rank, priority in enumerate(PRIORITIES)}
_IP_HEADER_BYTES = 64


@dataclass(frozen=True)
class EmergencyMessage:
    message_id: str
    sequence: int
    source: str
    destination: str
    content: str
    priority: str
    queued_at: str


@dataclass(frozen=True)
class PacketEvent:
    packet_id: str
    message_id: str
    source_ip: str
    destination_ip: str
    protocol: str
    packet_size_bytes: int
    timestamp: str
    status: str
    transmission_delay_ms: float | None
    priority: str
    route: tuple[str, ...]


def enqueue_message(
    queue: Iterable[EmergencyMessage],
    message: EmergencyMessage,
) -> list[EmergencyMessage]:
    if message.priority not in _PRIORITY_RANK:
        raise ValueError("Choose a supported emergency priority.")
    if message.source == message.destination:
        raise ValueError("Choose different sender and receiver services.")
    if not message.content.strip():
        raise ValueError("Enter a message before queueing it.")
    return order_messages([*queue, message])


def order_messages(queue: Iterable[EmergencyMessage]) -> list[EmergencyMessage]:
    messages = list(queue)
    if any(message.priority not in _PRIORITY_RANK for message in messages):
        raise ValueError("The priority queue contains an unsupported priority.")
    return sorted(
        messages,
        key=lambda item: (_PRIORITY_RANK[item.priority], item.sequence),
    )


def process_message(graph: nx.Graph, message: EmergencyMessage) -> PacketEvent:
    if message.source not in graph or message.destination not in graph:
        raise ValueError("Message endpoints must exist in the current topology.")

    packet_size = len(message.content.encode("utf-8")) + _IP_HEADER_BYTES
    try:
        plan = create_transmission_plan(
            graph,
            message.source,
            message.destination,
            message.content,
        )
    except nx.NetworkXNoPath:
        return PacketEvent(
            packet_id=f"PKT-{message.sequence:06d}",
            message_id=message.message_id,
            source_ip=graph.nodes[message.source]["address"],
            destination_ip=graph.nodes[message.destination]["address"],
            protocol="Emergency DATA/ACK",
            packet_size_bytes=packet_size,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
            status="Failed: no active route",
            transmission_delay_ms=None,
            priority=message.priority,
            route=(),
        )

    return PacketEvent(
        packet_id=f"PKT-{message.sequence:06d}",
        message_id=message.message_id,
        source_ip=graph.nodes[message.source]["address"],
        destination_ip=graph.nodes[message.destination]["address"],
        protocol="Emergency DATA/ACK",
        packet_size_bytes=plan.packet_size_bytes,
        timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
        status="Delivered",
        transmission_delay_ms=plan.estimated_delivery_delay_ms,
        priority=message.priority,
        route=plan.route,
    )
