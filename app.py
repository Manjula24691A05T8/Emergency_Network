from html import escape
from pathlib import Path

import networkx as nx

import plotly.graph_objects as go
import streamlit as st

from algorithms.go_back_n import GoBackNResult
from algorithms.sliding_window import SlidingWindowResult
from modules.network_topology import (
    CONTROL_CENTER,
    SERVICE_NODES,
    active_network,
    build_emergency_topology,
    build_topology_figure,
    get_topology_metrics,
)
from modules.message_transfer import PacketEvent
from modules.performance import summarize_packet_events


ROOT = Path(__file__).resolve().parent

st.set_page_config(
    page_title="Emergency Network Operations Center",
    page_icon=":material/emergency:",
    layout="wide",
    initial_sidebar_state="expanded",
)

stylesheet = ROOT / "assets" / "style.css"
st.markdown(f"<style>{stylesheet.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

failed_links = st.session_state.setdefault("failed_links", [])
failed_nodes = st.session_state.setdefault("failed_nodes", [])
topology = build_emergency_topology(failed_links, failed_nodes)
dashboard_metrics = st.session_state.get("dashboard_metrics", {})
if not isinstance(dashboard_metrics, dict):
    dashboard_metrics = {}
dashboard_metrics.update(get_topology_metrics(topology))
st.session_state["dashboard_metrics"] = dashboard_metrics

with st.sidebar:
    st.markdown(
        '<div class="sidebar-simulation"><span class="status-dot active"></span>'
        "<div><strong>SIMULATION MODE</strong>"
        "<span>Session data · no live connectivity</span></div></div>",
        unsafe_allow_html=True,
    )
    st.toggle(
        "Reduced motion",
        value=False,
        key="reduced_motion",
        help="Show the selected packet route without animated frames in 3D Infrastructure.",
    )
    st.markdown(
        '<div class="sidebar-brand">'
        '<div class="brand-mark">EN</div>'
        '<div><strong>E-NOC</strong><span>EMERGENCY NETWORK<br>OPERATIONS CENTER</span></div>'
        "</div>",
        unsafe_allow_html=True,
    )


def display_metric(value, suffix="", empty_text="Not run"):
    if value is None:
        return empty_text
    if isinstance(value, bool):
        return "Active" if value else "Inactive"
    if isinstance(value, int):
        return f"{value:,}{suffix}"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    return str(value)


def _dashboard_activity_figure(events: list[PacketEvent]) -> go.Figure:
    recent = sorted(events, key=lambda event: event.timestamp)[-20:]
    packet_ids = [event.packet_id for event in recent]
    statuses = [event.status for event in recent]
    colors = ["#55c79a" if status == "Delivered" else "#e06d70" for status in statuses]
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=packet_ids,
            y=[event.packet_size_bytes for event in recent],
            marker_color=colors,
            name="Packet size",
            customdata=[
                [event.status, event.priority, event.timestamp, " → ".join(event.route)]
                for event in recent
            ],
            hovertemplate=(
                "<b>%{x}</b><br>Size: %{y} bytes<br>Status: %{customdata[0]}"
                "<br>Priority: %{customdata[1]}<br>%{customdata[2]}"
                "<br>Route: %{customdata[3]}<extra></extra>"
            ),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=packet_ids,
            y=[event.transmission_delay_ms for event in recent],
            yaxis="y2",
            mode="lines+markers",
            line={"color": "#45c8e8", "width": 2},
            marker={"size": 7, "color": "#45c8e8"},
            name="Estimated DATA/ACK delay",
            connectgaps=False,
            hovertemplate="%{x}<br>Estimated delay: %{y:.2f} ms<extra></extra>",
        )
    )
    figure.update_layout(
        height=320,
        margin={"l": 12, "r": 16, "t": 20, "b": 42},
        paper_bgcolor="#101d2a",
        plot_bgcolor="#101d2a",
        font={"color": "#d5dfea", "family": "Inter, Segoe UI, sans-serif", "size": 11},
        legend={"orientation": "h", "x": 0.02, "y": 1.15},
        xaxis={"title": "Recent simulated packets", "gridcolor": "#243849"},
        yaxis={"title": "Packet size (bytes)", "gridcolor": "#243849", "rangemode": "tozero"},
        yaxis2={
            "title": "Estimated delay (ms)",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "rangemode": "tozero",
        },
        hoverlabel={"bgcolor": "#182a3b", "font": {"color": "#f4f8fb"}},
        barmode="overlay",
    )
    return figure


def _service_connectivity_markup(graph, reachable: set[str]) -> str:
    service_rows = []
    for node_id in SERVICE_NODES:
        if node_id == CONTROL_CENTER:
            continue
        node = graph.nodes[node_id]
        is_reachable = node_id in reachable
        status = "REACHABLE" if is_reachable else "UNAVAILABLE"
        state_class = "active" if is_reachable else "failed"
        service_rows.append(
            '<div class="service-row">'
            f'<span class="status-dot {state_class}"></span>'
            f'<span class="service-name">{escape(node["label"])}</span>'
            f'<span class="service-state {state_class}">{status}</span>'
            "</div>"
        )
    return "".join(service_rows)


def _device_status_markup(graph) -> str:
    rows = []
    for node_id, data in graph.nodes(data=True):
        if data.get("kind") not in {"router", "switch"}:
            continue
        is_active = data.get("status") == "active"
        state = "active" if is_active else "failed"
        active_links = sum(
            edge_data.get("status") == "active"
            for _, _, edge_data in graph.edges(node_id, data=True)
        )
        rows.append(
            '<div class="device-row">'
            f'<span class="status-dot {state}"></span>'
            f'<span class="device-name">{escape(data["short_label"])}'
            f'<small>{escape(data["role"])}</small></span>'
            f'<span class="device-state {state}">'
            f'{"ONLINE" if is_active else "FAILED"} · {active_links} LINKS</span>'
            "</div>"
        )
    return "".join(rows)


def render_dashboard():
    metrics = get_topology_metrics(topology)
    dashboard_metrics = st.session_state.get("dashboard_metrics", {})
    if isinstance(dashboard_metrics, dict):
        metrics["congestion_status"] = dashboard_metrics.get("congestion_status", "Not run")
    packet_events = st.session_state.get("packet_events", [])
    packet_records = (
        [event for event in packet_events if isinstance(event, PacketEvent)]
        if isinstance(packet_events, list)
        else []
    )
    message_performance = summarize_packet_events(packet_records)
    reliable_result = st.session_state.get("reliable_transmission_result")
    reliable_run = isinstance(reliable_result, (SlidingWindowResult, GoBackNResult))
    metrics["throughput_mbps"] = message_performance.modeled_throughput_mbps
    metrics.update(
        {
            "messages_sent": None,
            "messages_delivered": None,
            "packet_loss_percent": None,
            "route_delay_ms": None,
            "network_utilization_percent": None,
        }
    )
    if reliable_run:
        if isinstance(reliable_result, GoBackNResult):
            transmission_attempts = sum(
                len(round_result.transmitted) for round_result in reliable_result.rounds
            )
            dropped_attempts = sum(
                len(round_result.dropped) for round_result in reliable_result.rounds
            )
        else:
            transmission_attempts = sum(
                len(batch.transmitted) for batch in reliable_result.batches
            )
            dropped_attempts = 0

        route = st.session_state.get("reliable_transmission_route", ())
        route_is_active = (
            isinstance(route, (list, tuple))
            and bool(route)
            and all(
                topology.has_edge(first, second)
                and topology.edges[first, second]["status"] == "active"
                for first, second in zip(route, route[1:])
            )
        )
        metrics.update(
            {
                "messages_sent": reliable_result.packet_count,
                "messages_delivered": reliable_result.total_acknowledged,
                "packet_loss_percent": (
                    100 * dropped_attempts / transmission_attempts
                    if transmission_attempts
                    else None
                ),
                "route_delay_ms": (
                    st.session_state.get("reliable_transmission_route_delay_ms")
                    if route_is_active
                    else None
                ),
            }
        )
    failed_nodes = [
        node_id
        for node_id, data in topology.nodes(data=True)
        if data.get("status") == "failed"
    ]
    failed_edges = [
        (first, second)
        for first, second, data in topology.edges(data=True)
        if data["status"] == "failed"
        and topology.nodes[first].get("status") != "failed"
        and topology.nodes[second].get("status") != "failed"
    ]

    active_graph = active_network(topology)
    reachable = (
        nx.node_connected_component(active_graph, CONTROL_CENTER)
        if CONTROL_CENTER in active_graph
        else set()
    )

    st.markdown(
        '<div class="eyebrow">EMERGENCY NETWORK · OPERATIONS CENTER</div>',
        unsafe_allow_html=True,
    )
    header_col, status_col = st.columns([4, 1])
    with header_col:
        st.title("Network Operations Center")
        st.markdown(
            "Infrastructure health, service reachability, and simulated packet activity "
            "in one operational view."
        )
    with status_col:
        st.markdown(
            '<div class="session-status"><span class="status-dot active"></span>'
            "<div><strong>SIMULATION ACTIVE</strong>"
            "<span>Session-scoped data</span></div></div>",
            unsafe_allow_html=True,
        )

    health = metrics["network_health"]
    health_class = {
        "Operational": "operational",
        "Degraded": "degraded",
        "Critical": "critical",
    }.get(health, "unknown")
    health_ratio = (
        metrics["reachable_services"] / metrics["total_services"]
        if metrics["total_services"]
        else 0
    )
    health_panel_col, service_panel_col = st.columns([1.12, 1])
    with health_panel_col:
        st.markdown(
            '<div class="health-overview">'
            '<div class="panel-kicker">NETWORK HEALTH</div>'
            f'<div class="health-overview-status"><span class="health-pill {health_class}">'
            f"{escape(str(health))}</span>"
            f'<span class="health-overview-detail">{metrics["reachable_services"]} / '
            f'{metrics["total_services"]} services reachable</span></div>'
            '<div class="health-track"><span class="health-fill '
            f'{health_class}" style="width:{health_ratio * 100:.1f}%"></span></div>'
            '<div class="health-footnote">Reachability from the Emergency Control Center · '
            "calculated from active NetworkX links</div></div>",
            unsafe_allow_html=True,
        )
    with service_panel_col:
        st.markdown(
            '<div class="service-connectivity">'
            '<div class="panel-kicker">EMERGENCY SERVICE CONNECTIVITY</div>'
            f"{_service_connectivity_markup(topology, reachable)}"
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-heading">Infrastructure status</div>', unsafe_allow_html=True)
    infrastructure = (
        ("Network nodes", "total_nodes"),
        ("Active routers", "active_routers"),
        ("Active switches", "active_switches"),
        ("Active links", "active_connections"),
        ("Failed links", "failed_connections"),
    )
    columns = st.columns(len(infrastructure))
    for column, (label, key) in zip(columns, infrastructure):
        with column:
            st.metric(label, display_metric(metrics[key]))

    overview_col, operations_col = st.columns([1.6, 1])
    with overview_col:
        st.markdown('<div class="section-heading">Network activity map</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                '<div class="card-kicker">TOPOLOGY STATE · ROUTE HIGHLIGHTED FROM LATEST MESSAGE</div>',
                unsafe_allow_html=True,
            )
            latest_route = packet_records[0].route if packet_records else ()
            if not packet_records:
                latest_route = st.session_state.get("reliable_transmission_route", ())
            active_route = (
                latest_route
                if isinstance(latest_route, (list, tuple))
                and len(latest_route) > 1
                and all(
                    topology.has_edge(first, second)
                    and topology.edges[first, second]["status"] == "active"
                    for first, second in zip(latest_route, latest_route[1:])
                )
                else ()
            )
            figure = build_topology_figure(
                topology,
                highlighted_links=list(zip(active_route, active_route[1:])),
            )
            figure.update_layout(height=500)
            st.plotly_chart(
                figure,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True, "responsive": True},
                key="dashboard_topology_chart",
            )
            st.caption(
                "The map reflects current active and failed links. A green path is taken "
                "from the latest reachable simulated message."
            )

    with operations_col:
        st.markdown('<div class="section-heading">Operations watch</div>', unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown('<div class="card-kicker">ACTIVE NETWORK ALERTS</div>', unsafe_allow_html=True)
            if failed_nodes or failed_edges:
                for node_id in failed_nodes:
                    st.error(
                        f"{topology.nodes[node_id]['label']} is unavailable; "
                        "its attached connections are down."
                    )
                for first, second in failed_edges:
                    message = (
                        f"{topology.nodes[first]['label']} ↔ "
                        f"{topology.nodes[second]['label']} is unavailable."
                    )
                    if health == "Critical":
                        st.error(message)
                    else:
                        st.warning(message)
            else:
                st.markdown(
                    '<div class="no-alert"><span class="status-dot active"></span>'
                    "<span>No active infrastructure alerts</span></div>",
                    unsafe_allow_html=True,
                )
                st.caption(
                    f"{topology.number_of_edges()} simulated links are available. "
                    "Failure state is derived from the active topology."
                )
            congestion_status = metrics["congestion_status"]
            congestion_drops = dashboard_metrics.get("congestion_dropped_packets", 0)
            if congestion_status == "Congested":
                st.warning(
                    f"Leaky Bucket reported {congestion_drops} dropped packet(s) due to "
                    "buffer overflow."
                )
            elif congestion_status == "At capacity":
                st.warning("The latest Leaky Bucket run filled the router buffer.")
            elif congestion_status == "Not run":
                st.caption("Congestion monitoring is awaiting a Leaky Bucket simulation.")

        with st.container(border=True):
            st.markdown('<div class="card-kicker">ROUTER & SWITCH STATUS</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="device-status-list">{_device_status_markup(topology)}</div>',
                unsafe_allow_html=True,
            )

        with st.container(border=True):
            st.markdown('<div class="card-kicker">RECENT COMMUNICATION ACTIVITY</div>', unsafe_allow_html=True)
            activity = st.session_state.get("recent_activity", [])
            if isinstance(activity, list) and activity:
                for item in activity[:5]:
                    st.markdown(f'<div class="activity-row">{escape(str(item))}</div>', unsafe_allow_html=True)
            else:
                st.info(
                    "No activity recorded yet. Send a message or run a transmission "
                    "simulation to populate this feed."
                )

    st.markdown('<div class="section-heading">Emergency message monitoring</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="card-kicker">SESSION PACKET RECORDS · SIMULATED DATA / ACK EVENTS</div>', unsafe_allow_html=True)
        message_metrics = st.columns(4)
        message_metrics[0].metric("Messages processed", message_performance.total_packets)
        message_metrics[1].metric("Messages delivered", message_performance.delivered_packets)
        message_metrics[2].metric(
            "Message loss",
            display_metric(message_performance.packet_loss_ratio_percent, "%", "No data"),
        )
        message_metrics[3].metric(
            "Average message delay",
            display_metric(message_performance.average_delay_ms, " ms", "No data"),
        )
        if packet_records:
            st.plotly_chart(
                _dashboard_activity_figure(packet_records),
                width="stretch",
                config={"displaylogo": False, "responsive": True},
                key="dashboard_packet_activity",
            )
        else:
            st.info(
                "No packet records yet. Process an emergency message to see actual "
                "simulated packet size, delivery status, and estimated delay here."
            )

    st.markdown('<div class="section-heading">Reliable transmission performance</div>', unsafe_allow_html=True)
    with st.container(border=True):
        if reliable_run:
            protocol = st.session_state.get(
                "reliable_transmission_protocol",
                "Reliable transmission",
            )
            rounds = (
                len(reliable_result.rounds)
                if isinstance(reliable_result, GoBackNResult)
                else len(reliable_result.batches)
            )
            st.markdown(
                f'<div class="card-kicker">LATEST RUN · {escape(str(protocol)).upper()}</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                f"{reliable_result.total_acknowledged} of {reliable_result.packet_count} "
                f"frames acknowledged across {rounds} transmission rounds."
            )
        else:
            st.markdown('<div class="card-kicker">AWAITING A SIMULATION RUN</div>', unsafe_allow_html=True)
        transmission_metrics = (
            ("Frames sent", "messages_sent", ""),
            ("Frames acknowledged", "messages_delivered", ""),
            ("Frame loss (attempts)", "packet_loss_percent", "%"),
            ("Route RTT estimate", "route_delay_ms", " ms"),
        )
        columns = st.columns(4)
        for column, (label, key, suffix) in zip(columns, transmission_metrics):
            with column:
                unavailable = "Route unavailable" if key == "route_delay_ms" and reliable_run else "Not run"
                column.metric(
                    label,
                    display_metric(metrics.get(key), suffix, unavailable),
                )
        telemetry = st.columns(3)
        telemetry[0].metric(
            "Throughput",
            display_metric(
                metrics["throughput_mbps"],
                " Mbps",
                "No packet data",
            ),
            help=(
                "Estimated from delivered simulated payload-plus-header bits divided by "
                "the summed DATA/ACK delay. This is not measured link throughput."
            ),
        )
        telemetry[1].metric(
            "Bandwidth utilization",
            "Not modeled",
            help=(
                "Link utilization is not reported because the simulator does not model "
                "elapsed-time link capacity."
            ),
        )
        telemetry[2].metric("Congestion", metrics["congestion_status"])
        st.caption(
            "RTT is an estimated DATA/ACK route delay and excludes ARQ timeout waits. "
            "Throughput and link utilization are not calculated because this simulator "
            "does not model elapsed-time link capacity."
        )


def render_about():
    st.markdown('<div class="eyebrow">PROJECT BRIEF</div>', unsafe_allow_html=True)
    st.title("Reliable Emergency Communication Network")
    st.markdown(
        "An academic network simulation exploring how emergency-service nodes can "
        "exchange messages reliably when links are congested, lossy, or unavailable."
    )

    col_a, col_b = st.columns(2)
    with col_a:
        with st.container(border=True):
            st.markdown("### Engineering focus")
            st.markdown(
                "- Network topology and alternate paths\n"
                "- Dijkstra and distance-vector routing\n"
                "- Message priority and delivery status\n"
                "- CRC, sliding windows, and Go-Back-N\n"
                "- Leaky-bucket congestion control\n"
                "- Performance and packet analytics"
            )
    with col_b:
        with st.container(border=True):
            st.markdown("### Implementation status")
            st.markdown(
                "- **Stage 1:** Operations dashboard and topology-derived status\n"
                "- **Stage 2:** Interactive 3D network hardware scene\n"
                "- **Stage 3:** Dijkstra-routed DATA/ACK packet animation with optional loss and retry\n"
                "- **Stage 4:** Network failure and alternate routing visualization\n"
                "- **Stage 5:** Leaky Bucket congestion control and synchronized router queue\n"
                "- **Stage 6:** Sliding Window and Go-Back-N reliable transmission\n"
                "- **Stage 7:** Dashboard integration and final testing\n"
                "- **Communication:** Priority-ordered, route-aware simulated messages\n"
                "- **Monitoring:** Session packet records and computed performance analytics\n"
                "- **Data:** Simulated traffic only\n"
                "- **Connectivity:** No connection to real emergency services"
            )
    st.caption(
        "This application is an educational demonstration. It is not a production "
        "communications system and must not be used for real emergency response."
    )


page = st.navigation(
    {
        "Operations": [
            st.Page(render_dashboard, title="Dashboard", icon=":material/dashboard:"),
            st.Page("pages/topology.py", title="Network Topology", icon=":material/hub:"),
            st.Page("pages/topology_3d.py", title="3D Infrastructure", icon=":material/view_in_ar:"),
            st.Page("pages/routing.py", title="Routing Algorithms", icon=":material/alt_route:"),
            st.Page("pages/communication.py", title="Emergency Communication", icon=":material/priority_high:"),
            st.Page("pages/packet_monitor.py", title="Packet Monitoring", icon=":material/monitoring:"),
            st.Page("pages/congestion.py", title="Congestion Control", icon=":material/speed:"),
            st.Page("pages/analytics.py", title="Performance Analytics", icon=":material/analytics:"),
            st.Page("pages/error_detection.py", title="CRC Error Detection", icon=":material/rule:"),
            st.Page("pages/reliable_transmission.py", title="Reliable Transmission", icon=":material/swap_vert:"),
        ],
        "Project": [
            st.Page(render_about, title="About Project", icon=":material/info:"),
        ],
    },
    position="sidebar",
)
page.run()
