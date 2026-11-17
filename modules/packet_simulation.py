from dataclasses import dataclass
from typing import Mapping

import networkx as nx

from modules.network_topology import active_network


_IP_HEADER_BYTES = 64
_ACK_BYTES = 64


@dataclass(frozen=True)
class PacketTransmissionPlan:
    source: str
    destination: str
    message: str
    route: tuple[str, ...]
    packet_size_bytes: int
    one_way_delay_ms: float
    acknowledgement_delay_ms: float
    estimated_delivery_delay_ms: float
    retransmissions: int


def _link_delay_ms(edge: Mapping[str, float], packet_size_bytes: int) -> float:
    bandwidth_mbps = edge["bandwidth_mbps"]
    serialization_delay_ms = packet_size_bytes * 8 / (bandwidth_mbps * 1_000_000) * 1_000
    return edge["delay_ms"] + serialization_delay_ms


def create_transmission_plan(
    graph: nx.Graph,
    source: str,
    destination: str,
    message: str,
    inject_packet_loss: bool = False,
) -> PacketTransmissionPlan:
    if source not in graph or destination not in graph:
        raise ValueError("Source and destination must be nodes in the topology.")
    if source == destination:
        raise ValueError("Choose different source and destination devices.")
    if not message.strip():
        raise ValueError("Enter a message before preparing a transmission.")

    packet_size_bytes = len(message.encode("utf-8")) + _IP_HEADER_BYTES
    network = active_network(graph)
    for _, _, edge in network.edges(data=True):
        edge["route_cost_ms"] = _link_delay_ms(edge, packet_size_bytes)
    route = tuple(nx.dijkstra_path(network, source, destination, weight="route_cost_ms"))
    one_way_delay_ms = sum(
        _link_delay_ms(graph.edges[first, second], packet_size_bytes)
        for first, second in zip(route, route[1:])
    )
    reverse_route = tuple(reversed(route))
    acknowledgement_delay_ms = sum(
        _link_delay_ms(graph.edges[first, second], _ACK_BYTES)
        for first, second in zip(reverse_route, reverse_route[1:])
    )

    retransmissions = int(inject_packet_loss)
    failed_attempt_delay_ms = (
        _link_delay_ms(graph.edges[route[0], route[1]], packet_size_bytes) / 2
        if inject_packet_loss
        else 0.0
    )
    return PacketTransmissionPlan(
        source=source,
        destination=destination,
        message=message,
        route=route,
        packet_size_bytes=packet_size_bytes,
        one_way_delay_ms=one_way_delay_ms,
        acknowledgement_delay_ms=acknowledgement_delay_ms,
        estimated_delivery_delay_ms=(
            failed_attempt_delay_ms + one_way_delay_ms + acknowledgement_delay_ms
        ),
        retransmissions=retransmissions,
    )
