from itertools import islice
from typing import Iterable

import networkx as nx
import plotly.graph_objects as go


Link = tuple[str, str]

CONTROL_CENTER = "control_center"
SERVICE_NODES = (
    CONTROL_CENTER,
    "police_station",
    "fire_station",
    "ambulance_service",
    "rescue_team",
    "emergency_shelter",
)
NODE_DEFINITIONS = (
    (CONTROL_CENTER, "Emergency Control Center", "ECC", "service", "Command and dispatch", "10.20.0.10", -3.2, 1.5),
    ("police_station", "Police Station", "POLICE", "service", "Public safety", "10.20.0.11", -3.2, 0.35),
    ("fire_station", "Fire Station", "FIRE", "service", "Fire and rescue", "10.20.0.12", -3.2, -0.8),
    ("switch_north", "North Access Switch", "SW-N", "switch", "Access layer", "10.20.10.2", -1.45, 0.35),
    ("router_a", "Core Router A", "R-A", "router", "Core routing", "10.20.255.1", 0.1, 1.05),
    ("router_b", "Core Router B", "R-B", "router", "Core routing", "10.20.255.2", 0.1, -0.45),
    ("switch_south", "South Access Switch", "SW-S", "switch", "Access layer", "10.20.20.2", 1.65, 0.3),
    ("ambulance_service", "Ambulance Service", "EMS", "service", "Medical response", "10.20.0.13", 3.35, 1.35),
    ("rescue_team", "Rescue Team", "RESCUE", "service", "Search and rescue", "10.20.0.14", 3.35, 0.25),
    ("emergency_shelter", "Emergency Shelter", "SHELTER", "service", "Relief coordination", "10.20.0.15", 3.35, -0.85),
)
ROUTER_NODES = tuple(
    definition[0]
    for definition in NODE_DEFINITIONS
    if definition[3] == "router"
)

EDGE_DEFINITIONS = (
    (CONTROL_CENTER, "switch_north", 1000, 1.2),
    ("police_station", "switch_north", 100, 1.5),
    ("fire_station", "switch_north", 100, 1.8),
    ("ambulance_service", "switch_south", 100, 1.4),
    ("rescue_team", "switch_south", 100, 1.7),
    ("emergency_shelter", "switch_south", 100, 2.0),
    ("switch_north", "router_a", 1000, 0.8),
    ("switch_north", "router_b", 1000, 1.0),
    ("router_a", "router_b", 10000, 0.5),
    ("router_a", "switch_south", 1000, 0.9),
    ("router_b", "switch_south", 1000, 0.8),
)

NODE_COLORS = {
    "service": "#38b9d8",
    "router": "#4c8bf5",
    "switch": "#41d39b",
}


def canonical_link(first: str, second: str) -> Link:
    return tuple(sorted((first, second)))


def build_emergency_topology(
    failed_links: Iterable[Link] = (),
    failed_nodes: Iterable[str] = (),
) -> nx.Graph:
    requested_failures = {canonical_link(first, second) for first, second in failed_links}
    known_links = {canonical_link(first, second) for first, second, _, _ in EDGE_DEFINITIONS}
    unknown_links = requested_failures - known_links
    if unknown_links:
        raise ValueError(f"Unknown link failure(s): {sorted(unknown_links)}")
    requested_failed_nodes = set(failed_nodes)
    unknown_nodes = requested_failed_nodes - set(ROUTER_NODES)
    if unknown_nodes:
        raise ValueError(f"Unknown router failure(s): {sorted(unknown_nodes)}")

    graph = nx.Graph(name="Emergency communication network")
    for node_id, label, short_label, kind, role, address, x, y in NODE_DEFINITIONS:
        graph.add_node(
            node_id,
            label=label,
            short_label=short_label,
            kind=kind,
            role=role,
            address=address,
            x=x,
            y=y,
            status="failed" if node_id in requested_failed_nodes else "active",
        )

    for first, second, bandwidth_mbps, delay_ms in EDGE_DEFINITIONS:
        link_failed = (
            canonical_link(first, second) in requested_failures
            or first in requested_failed_nodes
            or second in requested_failed_nodes
        )
        graph.add_edge(
            first,
            second,
            bandwidth_mbps=bandwidth_mbps,
            delay_ms=delay_ms,
            status="failed" if link_failed else "active",
        )

    return graph


def active_network(graph: nx.Graph) -> nx.Graph:
    active = nx.Graph(name=graph.graph.get("name", "Emergency communication network"))
    active.add_nodes_from((node, data.copy()) for node, data in graph.nodes(data=True))
    active.add_edges_from(
        (first, second, data.copy())
        for first, second, data in graph.edges(data=True)
        if data.get("status") == "active"
    )
    return active


def get_available_paths(
    graph: nx.Graph,
    source: str,
    destination: str,
    limit: int = 4,
    max_hops: int = 6,
) -> list[list[str]]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if max_hops < 1:
        raise ValueError("max_hops must be at least 1")
    if source not in graph or destination not in graph:
        raise ValueError("Source and destination must be nodes in the topology")
    if source == destination:
        return [[source]]

    network = active_network(graph)
    if not nx.has_path(network, source, destination):
        return []

    paths = nx.all_simple_paths(network, source, destination, cutoff=max_hops)
    return list(islice(paths, limit))


def get_topology_metrics(graph: nx.Graph) -> dict[str, int | str]:
    network = active_network(graph)
    reachable = (
        nx.node_connected_component(network, CONTROL_CENTER)
        if CONTROL_CENTER in network
        else set()
    )
    unreachable_services = set(SERVICE_NODES) - reachable
    failed_connections = sum(
        1 for _, _, data in graph.edges(data=True) if data.get("status") != "active"
    )

    if unreachable_services:
        health = "Critical"
    elif failed_connections:
        health = "Degraded"
    else:
        health = "Operational"

    return {
        "total_nodes": graph.number_of_nodes(),
        "active_routers": sum(
            data.get("kind") == "router" and data.get("status") == "active"
            for _, data in graph.nodes(data=True)
        ),
        "active_switches": sum(
            data.get("kind") == "switch" and data.get("status") == "active"
            for _, data in graph.nodes(data=True)
        ),
        "active_connections": graph.number_of_edges() - failed_connections,
        "failed_connections": failed_connections,
        "reachable_services": len(set(SERVICE_NODES) & reachable),
        "total_services": len(SERVICE_NODES),
        "network_health": health,
    }


def build_topology_figure(
    graph: nx.Graph,
    highlighted_links: Iterable[Link] = (),
) -> go.Figure:
    highlighted = {canonical_link(first, second) for first, second in highlighted_links}
    figure = go.Figure()

    for first, second, data in graph.edges(data=True):
        first_data = graph.nodes[first]
        second_data = graph.nodes[second]
        link_status = data.get("status", "active")
        key = canonical_link(first, second)
        is_highlighted = link_status == "active" and key in highlighted
        color = (
            "#41d39b"
            if is_highlighted
            else "#f0525b"
            if link_status == "failed"
            else "#287da5"
        )
        figure.add_trace(
            go.Scatter(
                x=[first_data["x"], second_data["x"]],
                y=[first_data["y"], second_data["y"]],
                mode="lines",
                line={
                    "color": color,
                    "width": 4 if is_highlighted else 2.5,
                    "dash": "dash" if link_status == "failed" else "solid",
                },
                text=(
                    f"{first_data['label']} ↔ {second_data['label']}<br>"
                    f"Status: {link_status.title()}<br>"
                    f"Bandwidth: {data['bandwidth_mbps']:,} Mbps<br>"
                    f"Delay: {data['delay_ms']:.1f} ms"
                ),
                hovertemplate="%{text}<extra></extra>",
                showlegend=False,
            )
        )

    figure.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="lines",
            name="Active link",
            line={"color": "#287da5", "width": 3},
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=[None],
            y=[None],
            mode="lines",
            name="Failed link",
            line={"color": "#f0525b", "width": 3, "dash": "dash"},
            hoverinfo="skip",
        )
    )
    if highlighted:
        figure.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="lines",
                name="Available path",
                line={"color": "#41d39b", "width": 4},
                hoverinfo="skip",
            )
        )

    nodes = list(graph.nodes(data=True))
    figure.add_trace(
        go.Scatter(
            x=[data["x"] for _, data in nodes],
            y=[data["y"] for _, data in nodes],
            mode="markers+text",
            text=[data["short_label"] for _, data in nodes],
            textposition="bottom center",
            textfont={"size": 10, "color": "#dce8f1"},
            customdata=[
                [data["label"], data["role"], data["address"], data["status"]]
                for _, data in nodes
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Role: %{customdata[1]}<br>"
                "IP: %{customdata[2]}<br>"
                "Status: %{customdata[3]}<extra></extra>"
            ),
            marker={
                "size": 25,
                "color": [
                    "#f0525b"
                    if data.get("status") == "failed"
                    else NODE_COLORS[data["kind"]]
                    for _, data in nodes
                ],
                "symbol": [
                    "circle" if data["kind"] == "service"
                    else "diamond" if data["kind"] == "router"
                    else "square"
                    for _, data in nodes
                ],
                "line": {"color": "#dce8f1", "width": 1.2},
            },
            showlegend=False,
        )
    )

    figure.update_layout(
        height=570,
        margin={"l": 18, "r": 18, "t": 44, "b": 35},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        legend={"orientation": "h", "x": 0.02, "y": 1.08},
        hoverlabel={"bgcolor": "#102033", "font": {"color": "#e8f0f7"}},
        xaxis={"visible": False, "range": [-4.0, 4.1], "fixedrange": False},
        yaxis={
            "visible": False,
            "range": [-1.55, 2.15],
            "scaleanchor": "x",
            "scaleratio": 1,
            "fixedrange": False,
        },
        dragmode="pan",
    )
    return figure
