import plotly.graph_objects as go
import streamlit as st

from algorithms.leaky_bucket import LeakyBucketResult, simulate_leaky_bucket
from modules.network_topology import ROUTER_NODES, build_emergency_topology
from modules.traffic_input import parse_arrivals as _parse_arrivals


_DEFAULT_ARRIVALS = "2, 1, 8, 2, 7, 1, 6, 2"


def _traffic_figure(result: LeakyBucketResult) -> go.Figure:
    steps = result.steps
    ticks = [step.tick for step in steps]
    figure = go.Figure()
    figure.add_trace(
        go.Bar(
            x=ticks,
            y=[step.arrivals for step in steps],
            name="Incoming",
            marker_color="#3984a0",
        )
    )
    figure.add_trace(
        go.Bar(
            x=ticks,
            y=[step.transmitted for step in steps],
            name="Transmitted",
            marker_color="#41a982",
        )
    )
    figure.add_trace(
        go.Bar(
            x=ticks,
            y=[step.dropped for step in steps],
            name="Dropped",
            marker_color="#c65b5e",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=ticks,
            y=[step.queued_before_leak for step in steps],
            mode="lines+markers",
            name="Queue before output",
            line={"color": "#e2a04b", "width": 3},
            marker={"size": 7},
        )
    )
    figure.add_hline(
        y=result.capacity,
        line={"color": "#d75a5e", "dash": "dash", "width": 1.5},
        annotation_text=f"Buffer capacity · {result.capacity}",
        annotation_position="top left",
        annotation_font_color="#e69a9c",
    )
    figure.update_layout(
        barmode="group",
        height=390,
        margin={"l": 10, "r": 18, "t": 35, "b": 35},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        legend={"orientation": "h", "x": 0.02, "y": 1.12},
        xaxis={"title": "Time slot", "dtick": 1, "gridcolor": "#223342"},
        yaxis={"title": "Packets", "rangemode": "tozero", "gridcolor": "#223342"},
        hovermode="x unified",
    )
    return figure


def _render_result(result: LeakyBucketResult, graph) -> None:
    st.markdown('<div class="section-heading">Simulation results</div>', unsafe_allow_html=True)
    status = result.congestion_status
    summary = st.columns(5)
    summary[0].metric("Incoming packets", result.total_arrivals)
    summary[1].metric("Admitted", result.total_admitted)
    summary[2].metric("Transmitted", result.total_transmitted)
    summary[3].metric("Dropped", result.total_dropped)
    summary[4].metric("Congestion status", status)

    if result.total_dropped:
        st.warning(
            f"{result.total_dropped} packet(s) were dropped because the finite router "
            "buffer was full."
        )
    elif status == "At capacity":
        st.warning("The queue reached its full capacity, but no packets were dropped.")
    else:
        st.success("All admitted packets fit within the configured router buffer.")

    st.plotly_chart(
        _traffic_figure(result),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key="leaky_bucket_traffic_chart",
    )

    ticks = [step.tick for step in result.steps]
    peak_tick = max(result.steps, key=lambda step: step.queued_before_leak).tick
    if st.session_state.get("leaky_bucket_selected_tick") not in ticks:
        st.session_state["leaky_bucket_selected_tick"] = peak_tick
    selected_tick = st.slider(
        "Inspect queue snapshot",
        min_value=1,
        max_value=len(ticks),
        key="leaky_bucket_selected_tick",
        help="The 3D router queue displays packets waiting after arrivals and before output service.",
    )
    step = result.steps[selected_tick - 1]

    st.markdown('<div class="section-heading">Router buffer snapshot</div>', unsafe_allow_html=True)
    queue_columns = st.columns(5)
    router_id = st.session_state["leaky_bucket_router"]
    router_label = (
        graph.nodes[router_id]["short_label"]
        if router_id in graph
        else router_id
    )
    queue_columns[0].metric("Selected router", router_label)
    queue_columns[1].metric("Incoming this slot", step.arrivals)
    queue_columns[2].metric(
        "Queued before output",
        f"{step.queued_before_leak} / {result.capacity}",
    )
    queue_columns[3].metric("Transmitted this slot", step.transmitted)
    queue_columns[4].metric("Dropped this slot", step.dropped)
    st.progress(
        step.queued_before_leak / result.capacity,
        text=f"Queue occupancy · {step.queued_before_leak} of {result.capacity}",
    )
    st.caption(
        f"Slot {step.tick}: admitted {step.admitted}, then transmitted "
        f"{step.transmitted} packet(s); {step.queued_after_leak} remain queued."
    )
    if router_id in graph and graph.nodes[router_id]["status"] == "active":
        st.caption(
            "Open **3D Infrastructure** from the sidebar to inspect this slot's queue "
            "inside the selected router model."
        )
    else:
        st.warning(
            "The selected router has failed. Restore it or run a new simulation on an "
            "active router before viewing its queue in 3D."
        )


def render_congestion():
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])
    graph = build_emergency_topology(failed_links, failed_nodes)
    active_routers = [
        router for router in ROUTER_NODES if graph.nodes[router]["status"] == "active"
    ]

    st.markdown('<div class="eyebrow">TRAFFIC ENGINEERING / QUEUE MANAGEMENT</div>', unsafe_allow_html=True)
    st.title("Congestion Control")
    st.markdown(
        "Run a discrete-time Leaky Bucket simulation against a finite router buffer. "
        "Arrivals that exceed the available capacity are dropped; the configured output "
        "rate drains packets from the queue each time slot."
    )

    if not active_routers:
        st.error("No active router is available. Restore a router before running this simulation.")
        return

    with st.container(border=True):
        st.markdown('<div class="card-kicker">LEAKY BUCKET CONFIGURATION · SIMULATION ONLY</div>', unsafe_allow_html=True)
        with st.form("leaky_bucket_form"):
            router_col, capacity_col, rate_col = st.columns(3)
            router_id = router_col.selectbox(
                "Queue router",
                active_routers,
                format_func=lambda node: graph.nodes[node]["label"],
                key="leaky_bucket_router_input",
            )
            capacity = capacity_col.number_input(
                "Buffer capacity (packets)",
                min_value=1,
                max_value=40,
                value=8,
                step=1,
                key="leaky_bucket_capacity_input",
            )
            output_rate = rate_col.number_input(
                "Output rate (packets / slot)",
                min_value=1,
                max_value=40,
                value=2,
                step=1,
                key="leaky_bucket_rate_input",
            )
            traffic_pattern = st.text_input(
                "Incoming packets per time slot",
                value=_DEFAULT_ARRIVALS,
                key="leaky_bucket_arrivals_input",
                help="Enter up to 24 non-negative whole numbers separated by commas.",
            )
            submitted = st.form_submit_button("Run Leaky Bucket", type="primary")

    if submitted:
        try:
            arrivals = _parse_arrivals(traffic_pattern)
            result = simulate_leaky_bucket(arrivals, int(capacity), int(output_rate))
        except ValueError as error:
            st.error(f"Simulation not run: {error}")
        else:
            peak_tick = max(result.steps, key=lambda step: step.queued_before_leak).tick
            st.session_state["leaky_bucket_result"] = result
            st.session_state["leaky_bucket_router"] = router_id
            st.session_state["leaky_bucket_selected_tick"] = peak_tick
            dashboard_metrics = st.session_state.get("dashboard_metrics", {})
            if not isinstance(dashboard_metrics, dict):
                dashboard_metrics = {}
            dashboard_metrics["congestion_status"] = result.congestion_status
            dashboard_metrics["congestion_dropped_packets"] = result.total_dropped
            st.session_state["dashboard_metrics"] = dashboard_metrics
            activity = st.session_state.get("recent_activity", [])
            if not isinstance(activity, list):
                activity = []
            activity.insert(
                0,
                f"Leaky Bucket simulation on {graph.nodes[router_id]['short_label']}: "
                f"{result.total_transmitted} transmitted, {result.total_dropped} dropped.",
            )
            st.session_state["recent_activity"] = activity[:10]

    result = st.session_state.get("leaky_bucket_result")
    if isinstance(result, LeakyBucketResult):
        _render_result(result, graph)
    else:
        st.info("Configure the router buffer and run a simulation to inspect queue behavior.")


render_congestion()
