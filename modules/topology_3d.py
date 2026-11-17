from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

import networkx as nx
import plotly.graph_objects as go

from modules.network_topology import CONTROL_CENTER, active_network


_POSITION_SCALE = 1.75
_BOX_FACES = (
    (0, 2, 1), (0, 3, 2),
    (4, 5, 6), (4, 6, 7),
    (0, 1, 5), (0, 5, 4),
    (1, 2, 6), (1, 6, 5),
    (2, 3, 7), (2, 7, 6),
    (3, 0, 4), (3, 4, 7),
)

_MATERIALS = {
    "floor": "#151d24",
    "foundation": "#4b5358",
    "facility": "#707980",
    "roof": "#4c565d",
    "window": "#354751",
    "door": "#343b41",
    "cabinet": "#343b41",
    "metal": "#68737a",
    "panel": "#222a30",
    "port": "#10171b",
    "light_active": "#6f9a7f",
    "light_isolated": "#a27649",
    "switch": "#596970",
    "router": "#4e5961",
    "rack_unit": "#272f35",
}


@dataclass
class _MeshBuilder:
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    z: list[float] = field(default_factory=list)
    i: list[int] = field(default_factory=list)
    j: list[int] = field(default_factory=list)
    k: list[int] = field(default_factory=list)
    face_colors: list[str] = field(default_factory=list)

    def add_box(
        self,
        center: tuple[float, float, float],
        size: tuple[float, float, float],
        color: str,
    ) -> None:
        cx, cy, cz = center
        sx, sy, sz = size
        vertices = (
            (cx - sx / 2, cy - sy / 2, cz - sz / 2),
            (cx + sx / 2, cy - sy / 2, cz - sz / 2),
            (cx + sx / 2, cy + sy / 2, cz - sz / 2),
            (cx - sx / 2, cy + sy / 2, cz - sz / 2),
            (cx - sx / 2, cy - sy / 2, cz + sz / 2),
            (cx + sx / 2, cy - sy / 2, cz + sz / 2),
            (cx + sx / 2, cy + sy / 2, cz + sz / 2),
            (cx - sx / 2, cy + sy / 2, cz + sz / 2),
        )
        vertex_offset = len(self.x)
        for x_value, y_value, z_value in vertices:
            self.x.append(x_value)
            self.y.append(y_value)
            self.z.append(z_value)
        for face in _BOX_FACES:
            self.i.append(vertex_offset + face[0])
            self.j.append(vertex_offset + face[1])
            self.k.append(vertex_offset + face[2])
            self.face_colors.append(color)

    def to_trace(self, name: str) -> go.Mesh3d | None:
        if not self.x:
            return None
        return go.Mesh3d(
            x=self.x,
            y=self.y,
            z=self.z,
            i=self.i,
            j=self.j,
            k=self.k,
            facecolor=self.face_colors,
            flatshading=True,
            lighting={
                "ambient": 0.72,
                "diffuse": 0.78,
                "fresnel": 0.04,
                "roughness": 0.86,
                "specular": 0.16,
            },
            lightposition={"x": 400, "y": 550, "z": 800},
            name=name,
            hoverinfo="skip",
            showlegend=False,
            meta={"kind": "hardware"},
        )


def _scaled_position(graph: nx.Graph, node_id: str) -> tuple[float, float]:
    node = graph.nodes[node_id]
    return node["x"] * _POSITION_SCALE, node["y"] * _POSITION_SCALE


def _add_facility(
    builders: dict[str, _MeshBuilder],
    graph: nx.Graph,
    node_id: str,
    detailed: bool,
    reachable: bool,
) -> tuple[float, float, float]:
    node = graph.nodes[node_id]
    x, y = _scaled_position(graph, node_id)
    wall_color = {
        "control_center": "#78828a",
        "police_station": "#68747b",
        "fire_station": "#686d71",
        "ambulance_service": "#79848a",
        "rescue_team": "#6e777b",
        "emergency_shelter": "#85857b",
    }.get(node_id, _MATERIALS["facility"])
    z_wall = 0.66
    front_y = y + 0.66

    builders["foundation"].add_box((x, y, 0.10), (1.95, 1.52, 0.20), _MATERIALS["foundation"])
    builders["facility"].add_box((x, y, z_wall), (1.78, 1.32, 1.12), wall_color)
    builders["roof"].add_box((x, y, 1.27), (1.92, 1.46, 0.12), _MATERIALS["roof"])
    builders["door"].add_box((x + 0.47, front_y + 0.025, 0.48), (0.34, 0.05, 0.77), _MATERIALS["door"])
    builders["window"].add_box((x - 0.47, front_y + 0.025, 0.81), (0.43, 0.045, 0.31), _MATERIALS["window"])
    if detailed:
        builders["window"].add_box((x + 0.04, front_y + 0.025, 0.81), (0.35, 0.045, 0.31), _MATERIALS["window"])
        builders["metal"].add_box((x - 0.47, front_y + 0.055, 0.81), (0.025, 0.02, 0.35), "#59636a")
        builders["metal"].add_box((x - 0.47, front_y + 0.055, 0.81), (0.47, 0.02, 0.025), "#59636a")
    builders["metal"].add_box(
        (x - 0.59, front_y + 0.055, 1.12),
        (0.65, 0.035, 0.10),
        "#4c565d",
    )
    builders["status"].add_box(
        (x - 0.83, front_y + 0.08, 1.12),
        (0.045, 0.035, 0.045),
        _MATERIALS["light_active"] if reachable else _MATERIALS["light_isolated"],
    )
    return x, y, 1.56


def _add_front_ports(
    builders: dict[str, _MeshBuilder],
    x: float,
    front_y: float,
    z: float,
    width: float,
    count: int,
    indicator_color: str,
) -> None:
    usable_width = width * 0.78
    left = x - usable_width / 2
    spacing = usable_width / max(count, 1)
    for index in range(count):
        port_x = left + spacing * (index + 0.5)
        builders["port"].add_box(
            (port_x, front_y, z),
            (spacing * 0.62, 0.035, 0.065),
            _MATERIALS["port"],
        )
        builders["status"].add_box(
            (port_x, front_y + 0.021, z + 0.055),
            (0.022, 0.018, 0.018),
            indicator_color if index % 4 == 0 else "#525e63",
        )


def _add_router_rack(
    builders: dict[str, _MeshBuilder],
    graph: nx.Graph,
    node_id: str,
    detailed: bool,
    reachable: bool,
    failed: bool,
) -> tuple[float, float, float]:
    x, y = _scaled_position(graph, node_id)
    cabinet_width, cabinet_depth, cabinet_height = 1.02, 0.80, 2.20
    front_y = y + cabinet_depth / 2 + 0.025
    builders["cabinet"].add_box(
        (x, y, cabinet_height / 2),
        (cabinet_width, cabinet_depth, cabinet_height),
        _MATERIALS["cabinet"],
    )
    for rail_x in (x - 0.43, x + 0.43):
        builders["metal"].add_box(
            (rail_x, front_y + 0.035, 1.08),
            (0.045, 0.055, 1.96),
            _MATERIALS["metal"],
        )

    chassis_centers = (0.75, 1.48)
    for chassis_z in chassis_centers:
        builders["router"].add_box(
            (x, front_y + 0.045, chassis_z),
            (0.82, 0.12, 0.32),
            _MATERIALS["router"],
        )
        builders["panel"].add_box(
            (x, front_y + 0.11, chassis_z),
            (0.74, 0.025, 0.25),
            _MATERIALS["panel"],
        )
        _add_front_ports(
            builders,
            x,
            front_y + 0.13,
            chassis_z - 0.035,
            0.69,
            8 if detailed else 4,
            "#d75a5e"
            if failed
            else _MATERIALS["light_active"]
            if reachable
            else _MATERIALS["light_isolated"],
        )
        builders["status"].add_box(
            (x + 0.34, front_y + 0.16, chassis_z + 0.065),
            (0.028, 0.018, 0.02),
            "#d75a5e"
            if failed
            else _MATERIALS["light_active"]
            if reachable
            else _MATERIALS["light_isolated"],
        )

    unit_count = 12 if detailed else 6
    for index in range(unit_count):
        unit_z = 0.22 + index * (1.78 / unit_count)
        builders["metal"].add_box(
            (x, front_y + 0.015, unit_z),
            (0.72, 0.025, 0.025),
            "#4f5b62",
        )
    return x, y, 2.32


def _add_switch(
    builders: dict[str, _MeshBuilder],
    graph: nx.Graph,
    node_id: str,
    detailed: bool,
    reachable: bool,
) -> tuple[float, float, float]:
    x, y = _scaled_position(graph, node_id)
    width, depth = 1.62, 0.68
    body_z = 0.58
    front_y = y + depth / 2 + 0.035
    builders["foundation"].add_box((x, y, 0.12), (1.74, 0.78, 0.20), "#343d43")
    builders["switch"].add_box((x, y, body_z), (width, depth, 0.28), _MATERIALS["switch"])
    builders["panel"].add_box((x, front_y, body_z), (1.52, 0.04, 0.22), _MATERIALS["panel"])
    _add_front_ports(
        builders,
        x,
        front_y + 0.025,
        body_z - 0.015,
        1.46,
        16 if detailed else 8,
        _MATERIALS["light_active"] if reachable else _MATERIALS["light_isolated"],
    )
    return x, y, 0.92


def _add_server_rack(
    builders: dict[str, _MeshBuilder],
    center: tuple[float, float],
    detailed: bool,
) -> None:
    x, y = center
    width, depth, height = 0.76, 0.66, 2.06
    front_y = y + depth / 2 + 0.025
    builders["cabinet"].add_box(
        (x, y, height / 2),
        (width, depth, height),
        "#313a40",
    )
    for rail_x in (x - 0.30, x + 0.30):
        builders["metal"].add_box(
            (rail_x, front_y + 0.03, 1.02),
            (0.04, 0.05, 1.85),
            _MATERIALS["metal"],
        )
    unit_count = 10 if detailed else 5
    for index in range(unit_count):
        unit_z = 0.24 + index * (1.60 / unit_count)
        unit_height = 0.12 if detailed else 0.19
        builders["rack_unit"].add_box(
            (x, front_y + 0.035, unit_z),
            (0.52, 0.07, unit_height),
            _MATERIALS["rack_unit"],
        )
        if detailed:
            builders["metal"].add_box(
                (x - 0.13, front_y + 0.075, unit_z),
                (0.18, 0.018, 0.018),
                "#58636a",
            )
            builders["status"].add_box(
                (x + 0.20, front_y + 0.075, unit_z),
                (0.022, 0.018, 0.022),
                _MATERIALS["light_active"],
            )


def _add_tower(
    x: float,
    y: float,
    detailed: bool,
) -> go.Scatter3d:
    base_width = 0.56
    top_width = 0.19
    tower_height = 4.2
    xs: list[float | None] = []
    ys: list[float | None] = []
    zs: list[float | None] = []

    def add_segment(first: tuple[float, float, float], second: tuple[float, float, float]) -> None:
        xs.extend((first[0], second[0], None))
        ys.extend((first[1], second[1], None))
        zs.extend((first[2], second[2], None))

    levels = (0.0, 0.25, 0.5, 0.75, 1.0)
    for side_x in (-1, 1):
        for side_y in (-1, 1):
            add_segment(
                (x + side_x * base_width / 2, y + side_y * base_width / 2, 0.12),
                (x + side_x * top_width / 2, y + side_y * top_width / 2, tower_height),
            )

    for level in levels:
        width = base_width + (top_width - base_width) * level
        z = 0.12 + tower_height * level
        corners = (
            (x - width / 2, y - width / 2, z),
            (x + width / 2, y - width / 2, z),
            (x + width / 2, y + width / 2, z),
            (x - width / 2, y + width / 2, z),
        )
        for index in range(4):
            add_segment(corners[index], corners[(index + 1) % 4])

    brace_levels = levels if detailed else (0.0, 0.5, 1.0)
    for lower, upper in zip(brace_levels, brace_levels[1:]):
        lower_width = base_width + (top_width - base_width) * lower
        upper_width = base_width + (top_width - base_width) * upper
        z_lower = 0.12 + tower_height * lower
        z_upper = 0.12 + tower_height * upper
        for side_y in (-1, 1):
            add_segment(
                (x - lower_width / 2, y + side_y * lower_width / 2, z_lower),
                (x + upper_width / 2, y + side_y * upper_width / 2, z_upper),
            )
            add_segment(
                (x + lower_width / 2, y + side_y * lower_width / 2, z_lower),
                (x - upper_width / 2, y + side_y * upper_width / 2, z_upper),
            )

    add_segment((x, y, tower_height + 0.12), (x, y, tower_height + 0.68))
    add_segment(
        (x - 0.48, y, tower_height + 0.36),
        (x + 0.48, y, tower_height + 0.36),
    )
    return go.Scatter3d(
        x=xs,
        y=ys,
        z=zs,
        mode="lines",
        line={"color": "#78848a", "width": 3},
        name="Site communications tower",
        hovertemplate=(
            "<b>Rescue site communications tower</b><br>"
            "Facility asset; not a separate routed network node.<extra></extra>"
        ),
        meta={"kind": "site_asset", "name": "communications_tower"},
        showlegend=False,
    )


def _cable_endpoint(graph: nx.Graph, node_id: str) -> tuple[float, float, float]:
    x, y = _scaled_position(graph, node_id)
    kind = graph.nodes[node_id]["kind"]
    if kind == "service":
        return x, y + 0.69, 0.75
    if kind == "switch":
        return x, y + 0.39, 0.58
    return x, y + 0.50, 1.45


def _sample_polyline(
    points: Sequence[tuple[float, float, float]],
    subdivisions: int = 4,
) -> list[tuple[float, float, float]]:
    samples = []
    for start, end in zip(points, points[1:]):
        for step in range(subdivisions):
            ratio = step / subdivisions
            samples.append(
                tuple(
                    start[axis] + (end[axis] - start[axis]) * ratio
                    for axis in range(3)
                )
            )
    samples.append(points[-1])
    return samples


def add_packet_animation(
    figure: go.Figure,
    graph: nx.Graph,
    route: Sequence[str],
    inject_packet_loss: bool = False,
    reduced_motion: bool = False,
) -> go.Figure:
    if len(route) < 2:
        raise ValueError("A packet animation requires at least one network link.")

    hop_positions = []
    for first, second in zip(route, route[1:]):
        if not graph.has_edge(first, second) or graph.edges[first, second].get("status") != "active":
            raise ValueError(f"The route contains an unavailable link: {first} - {second}.")
        start = _cable_endpoint(graph, first)
        end = _cable_endpoint(graph, second)
        hop_positions.append(
            _sample_polyline(
                (
                    start,
                    (start[0], start[1], 0.10),
                    (end[0], end[1], 0.10),
                    end,
                )
            )
        )

    route_positions = []
    for index, hop in enumerate(hop_positions):
        route_positions.extend(hop if index == 0 else hop[1:])
        if index < len(hop_positions) - 1:
            route_positions.extend([hop[-1]] * 3)

    def packet_height(point: tuple[float, float, float]) -> tuple[float, float, float]:
        return point[0], point[1], point[2] + 0.18

    route_x: list[float | None] = []
    route_y: list[float | None] = []
    route_z: list[float | None] = []
    for hop in hop_positions:
        route_x.extend([point[0] for point in hop] + [None])
        route_y.extend([point[1] for point in hop] + [None])
        route_z.extend([point[2] for point in hop] + [None])
    figure.add_trace(
        go.Scatter3d(
            x=route_x,
            y=route_y,
            z=route_z,
            mode="lines",
            line={"color": "#38a9c5", "width": 7},
            name="Selected Dijkstra route",
            hoverinfo="skip",
            meta={"kind": "packet_route", "route": list(route)},
            showlegend=True,
        )
    )

    packet_trace_index = len(figure.data)
    packet_start = packet_height(route_positions[0])
    figure.add_trace(
        go.Scatter3d(
            x=[packet_start[0]],
            y=[packet_start[1]],
            z=[packet_start[2]],
            mode="markers+text",
            marker={"size": 14, "color": "#a8f4ff", "line": {"color": "#f2fbfc", "width": 1}},
            text=["DATA"],
            textposition="top center",
            textfont={"size": 10, "color": "#d9eef2"},
            name="Data packet",
            meta={"kind": "animated_packet", "protocol": "data"},
            showlegend=False,
        )
    )
    acknowledgement_trace_index = len(figure.data)
    figure.add_trace(
        go.Scatter3d(
            x=[None],
            y=[None],
            z=[None],
            mode="markers+text",
            marker={"size": 10, "color": "#63d9a2", "line": {"color": "#e6f4ed", "width": 1}},
            text=["ACK"],
            textposition="top center",
            textfont={"size": 9, "color": "#d5eee3"},
            name="Acknowledgement",
            meta={"kind": "animated_packet", "protocol": "ack"},
            showlegend=False,
        )
    )
    dropped_trace_index = len(figure.data)
    figure.add_trace(
        go.Scatter3d(
            x=[None],
            y=[None],
            z=[None],
            mode="markers+text",
            marker={"size": 9, "color": "#d46a62", "symbol": "x"},
            text=["DROP"],
            textposition="top center",
            textfont={"size": 9, "color": "#f0aaa2"},
            name="Dropped packet",
            meta={"kind": "animated_packet", "protocol": "drop"},
            showlegend=False,
        )
    )
    dynamic_trace_indices = [
        packet_trace_index,
        acknowledgement_trace_index,
        dropped_trace_index,
    ]
    if reduced_motion:
        destination_position = packet_height(route_positions[-1])
        source_position = packet_height(route_positions[0])
        packet_trace = figure.data[packet_trace_index]
        packet_trace.x = [destination_position[0]]
        packet_trace.y = [destination_position[1]]
        packet_trace.z = [destination_position[2]]
        acknowledgement_trace = figure.data[acknowledgement_trace_index]
        acknowledgement_trace.x = [source_position[0]]
        acknowledgement_trace.y = [source_position[1]]
        acknowledgement_trace.z = [source_position[2]]
        if inject_packet_loss:
            first_attempt = hop_positions[0]
            drop_position = packet_height(first_attempt[len(first_attempt) // 2])
            dropped_trace = figure.data[dropped_trace_index]
            dropped_trace.x = [drop_position[0]]
            dropped_trace.y = [drop_position[1]]
            dropped_trace.z = [drop_position[2]]
        figure.frames = ()
        figure.update_layout(margin={"t": 64}, updatemenus=[])
        return figure

    frames = []

    def add_frame(
        packet: tuple[float, float, float] | None,
        acknowledgement: tuple[float, float, float] | None = None,
        dropped: tuple[float, float, float] | None = None,
    ) -> None:
        positions = tuple(
            packet_height(point) if point is not None else None
            for point in (packet, acknowledgement, dropped)
        )
        frame_data = [
            go.Scatter3d(
                x=[point[0]] if point else [None],
                y=[point[1]] if point else [None],
                z=[point[2]] if point else [None],
            )
            for point in positions
        ]
        frames.append(
            go.Frame(
                name=f"packet_{len(frames)}",
                data=frame_data,
                traces=dynamic_trace_indices,
            )
        )

    if inject_packet_loss:
        first_attempt = hop_positions[0]
        drop_position = first_attempt[len(first_attempt) // 2]
        for point in first_attempt[1 : len(first_attempt) // 2 + 1]:
            add_frame(point)
        for _ in range(5):
            add_frame(None, dropped=drop_position)
        add_frame(route_positions[0])

    for point in route_positions[1:]:
        add_frame(point)
    destination_position = route_positions[-1]
    for point in reversed(route_positions):
        add_frame(destination_position, acknowledgement=point)

    figure.frames = tuple(frames)
    figure.update_layout(
        margin={"t": 64},
        updatemenus=[
            {
                "type": "buttons",
                "direction": "right",
                "showactive": False,
                "bgcolor": "#18232b",
                "bordercolor": "#31414a",
                "borderwidth": 1,
                "font": {"color": "#dce8f1", "size": 12},
                "x": 0.02,
                "xanchor": "left",
                "y": 0.92,
                "buttons": [
                    {
                        "label": "Play transmission",
                        "method": "animate",
                        "args": [
                            None,
                            {
                                "frame": {"duration": 55, "redraw": True},
                                "transition": {"duration": 0},
                                "fromcurrent": True,
                                "mode": "immediate",
                            },
                        ],
                    },
                    {
                        "label": "Reset",
                        "method": "animate",
                        "args": [
                            [frames[0].name],
                            {
                                "frame": {"duration": 0, "redraw": True},
                                "transition": {"duration": 0},
                                "mode": "immediate",
                            },
                        ],
                    },
                ],
            }
        ]
    )
    return figure


def build_3d_topology_figure(graph: nx.Graph, reduced_detail: bool = False) -> go.Figure:
    detailed = not reduced_detail
    network = active_network(graph)
    reachable = (
        nx.node_connected_component(network, CONTROL_CENTER)
        if CONTROL_CENTER in network
        else set()
    )
    builders = {
        name: _MeshBuilder()
        for name in (
            "floor",
            "foundation",
            "facility",
            "roof",
            "window",
            "door",
            "cabinet",
            "metal",
            "panel",
            "port",
            "status",
            "switch",
            "router",
            "rack_unit",
        )
    }

    builders["floor"].add_box((0, 0, -0.12), (18, 13, 0.20), _MATERIALS["floor"])

    node_labels: list[tuple[str, float, float, float, str, bool]] = []
    for node_id, data in graph.nodes(data=True):
        is_reachable = node_id in reachable
        is_failed = data.get("status") == "failed"
        if data["kind"] == "service":
            x, y, label_z = _add_facility(builders, graph, node_id, detailed, is_reachable)
            if node_id == CONTROL_CENTER:
                _add_server_rack(builders, (x + 1.38, y + 0.04), detailed)
        elif data["kind"] == "router":
            x, y, label_z = _add_router_rack(
                builders,
                graph,
                node_id,
                detailed,
                is_reachable,
                is_failed,
            )
        else:
            x, y, label_z = _add_switch(
                builders,
                graph,
                node_id,
                detailed,
                is_reachable,
            )
        node_labels.append(
            (
                node_id,
                x,
                y,
                label_z,
                "#d75a5e"
                if is_failed
                else _MATERIALS["light_active"]
                if is_reachable
                else _MATERIALS["light_isolated"],
                is_failed,
            )
        )

    rescue_x, rescue_y = _scaled_position(graph, "rescue_team")
    tower_x, tower_y = rescue_x + 1.25, rescue_y - 0.05
    builders["foundation"].add_box(
        (tower_x, tower_y, 0.04),
        (0.82, 0.82, 0.08),
        _MATERIALS["foundation"],
    )

    figure = go.Figure()
    mesh_names = {
        "floor": "Operations floor",
        "foundation": "Equipment bases",
        "facility": "Emergency service buildings",
        "roof": "Building roofs",
        "window": "Windows",
        "door": "Doors",
        "cabinet": "Equipment cabinets",
        "metal": "Metal hardware",
        "panel": "Front panels",
        "port": "Network ports",
        "status": "Device indicators",
        "switch": "Access switches",
        "router": "Enterprise routers",
        "rack_unit": "Server rack units",
    }
    for group_name, builder in builders.items():
        trace = builder.to_trace(mesh_names[group_name])
        if trace is not None:
            figure.add_trace(trace)

    figure.add_trace(
        go.Scatter3d(
            x=[None],
            y=[None],
            z=[None],
            mode="lines",
            name="Active network cable",
            line={"color": "#748a95", "width": 4},
            hoverinfo="skip",
            showlegend=True,
        )
    )
    figure.add_trace(
        go.Scatter3d(
            x=[None],
            y=[None],
            z=[None],
            mode="lines",
            name="Failed network cable",
            line={"color": "#b65b5e", "width": 4, "dash": "dash"},
            hoverinfo="skip",
            showlegend=True,
        )
    )

    for first, second, data in graph.edges(data=True):
        start = _cable_endpoint(graph, first)
        end = _cable_endpoint(graph, second)
        status = data.get("status", "active")
        color = "#748a95" if status == "active" else "#b65b5e"
        ground_height = 0.10
        figure.add_trace(
            go.Scatter3d(
                x=[start[0], start[0], end[0], end[0]],
                y=[start[1], start[1], end[1], end[1]],
                z=[start[2], ground_height, ground_height, end[2]],
                mode="lines",
                line={
                    "color": color,
                    "width": 4,
                    "dash": "solid" if status == "active" else "dash",
                },
                text=(
                    f"{graph.nodes[first]['label']} ↔ {graph.nodes[second]['label']}<br>"
                    f"Status: {status.title()}<br>"
                    f"Bandwidth: {data['bandwidth_mbps']:,} Mbps<br>"
                    f"Delay: {data['delay_ms']:.1f} ms"
                ),
                hovertemplate="%{text}<extra></extra>",
                name=f"{first} - {second}",
                meta={
                    "kind": "cable",
                    "link": (first, second),
                    "status": status,
                },
                showlegend=False,
            )
        )

    if not reduced_detail:
        grid_x: list[float | None] = []
        grid_y: list[float | None] = []
        grid_z: list[float | None] = []
        for x_value in range(-8, 9, 2):
            grid_x.extend((x_value, x_value, None))
            grid_y.extend((-5.5, 5.5, None))
            grid_z.extend((0.002, 0.002, None))
        for y_value in range(-5, 6, 2):
            grid_x.extend((-8.5, 8.5, None))
            grid_y.extend((y_value, y_value, None))
            grid_z.extend((0.002, 0.002, None))
        figure.add_trace(
            go.Scatter3d(
                x=grid_x,
                y=grid_y,
                z=grid_z,
                mode="lines",
                line={"color": "#27323a", "width": 1},
                hoverinfo="skip",
                showlegend=False,
                meta={"kind": "floor_grid"},
            )
        )

    figure.add_trace(_add_tower(tower_x, tower_y, detailed))

    figure.add_trace(
        go.Scatter3d(
            x=[item[1] for item in node_labels],
            y=[item[2] for item in node_labels],
            z=[item[3] for item in node_labels],
            mode="markers+text",
            marker={
                "size": [7 if item[5] else 4 for item in node_labels],
                "color": [item[4] for item in node_labels],
                "symbol": ["x" if item[5] else "circle" for item in node_labels],
            },
            text=[graph.nodes[item[0]]["short_label"] for item in node_labels],
            textposition="top center",
            textfont={"size": 10, "color": "#d9e0e4"},
            customdata=[
                [
                    graph.nodes[item[0]]["label"],
                    graph.nodes[item[0]]["role"],
                    graph.nodes[item[0]]["address"],
                    "Reachable" if item[0] in reachable else "Isolated",
                    graph.nodes[item[0]].get("status", "active").title(),
                ]
                for item in node_labels
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Role: %{customdata[1]}<br>"
                "IP: %{customdata[2]}<br>"
                "Connectivity: %{customdata[3]}<br>"
                "Device status: %{customdata[4]}<extra></extra>"
            ),
            name="Network devices",
            meta={"kind": "device_labels"},
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter3d(
            x=[tower_x],
            y=[tower_y],
            z=[4.82],
            mode="text",
            text=["RADIO TOWER"],
            textposition="top center",
            textfont={"size": 9, "color": "#aab4ba"},
            hoverinfo="skip",
            showlegend=False,
        )
    )

    figure.update_layout(
        height=600,
        margin={"l": 0, "r": 0, "t": 28, "b": 0},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        hoverlabel={"bgcolor": "#18232b", "font": {"color": "#e8f0f7"}},
        legend={
            "orientation": "h",
            "x": 0.02,
            "y": 1.02,
            "bgcolor": "rgba(12, 25, 40, 0.85)",
        },
        scene={
            "bgcolor": "#0c1928",
            "aspectmode": "manual",
            "aspectratio": {"x": 1.7, "y": 1.2, "z": 0.82},
            "camera": {
                "eye": {"x": 1.65, "y": 1.6, "z": 1.15},
                "up": {"x": 0, "y": 0, "z": 1},
            },
            "dragmode": "orbit",
            "xaxis": {"visible": False, "range": [-9.0, 9.0]},
            "yaxis": {"visible": False, "range": [-6.5, 6.5]},
            "zaxis": {"visible": False, "range": [-0.2, 5.3]},
        },
        uirevision="emergency-network-3d",
    )
    return figure


def add_router_queue_visualization(
    figure: go.Figure,
    graph: nx.Graph,
    router_id: str,
    occupancy: int,
    capacity: int,
    tick: int,
) -> go.Figure:
    if router_id not in graph or graph.nodes[router_id].get("kind") != "router":
        raise ValueError("Queue visualization requires a router in the topology.")
    if graph.nodes[router_id].get("status") != "active":
        raise ValueError("Cannot display an active packet queue on a failed router.")
    if (
        not isinstance(capacity, int)
        or isinstance(capacity, bool)
        or capacity < 1
        or not isinstance(occupancy, int)
        or isinstance(occupancy, bool)
        or occupancy < 0
        or occupancy > capacity
    ):
        raise ValueError("Queue occupancy must be between zero and its positive capacity.")
    if not isinstance(tick, int) or isinstance(tick, bool) or tick < 1:
        raise ValueError("Queue snapshot tick must be positive.")

    x, y = _scaled_position(graph, router_id)
    queue_x = x + 0.66
    queue_y = y + 0.53
    slot_spacing = 1.65 / max(capacity - 1, 1)
    slot_heights = [0.28 + index * slot_spacing for index in range(capacity)]
    full = occupancy == capacity
    active_color = "#d75a5e" if full else "#e2a04b"
    figure.add_trace(
        go.Scatter3d(
            x=[queue_x] * capacity,
            y=[queue_y] * capacity,
            z=slot_heights,
            mode="markers",
            marker={
                "size": 8,
                "symbol": "square",
                "color": [
                    active_color if index < occupancy else "#46525a"
                    for index in range(capacity)
                ],
                "line": {"color": "#aeb9bf", "width": 0.5},
            },
            text=[
                f"Queued packet {index + 1}"
                if index < occupancy
                else "Available buffer slot"
                for index in range(capacity)
            ],
            hovertemplate="%{text}<extra></extra>",
            name=f"{graph.nodes[router_id]['short_label']} packet queue",
            meta={
                "kind": "router_queue",
                "router": router_id,
                "occupancy": occupancy,
                "capacity": capacity,
                "tick": tick,
            },
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter3d(
            x=[queue_x],
            y=[queue_y],
            z=[2.18],
            mode="text",
            text=[f"Q {occupancy}/{capacity} · T{tick}"],
            textfont={"size": 10, "color": active_color},
            hoverinfo="skip",
            name="Router queue status",
            meta={"kind": "router_queue_status", "router": router_id, "full": full},
            showlegend=False,
        )
    )
    return figure
