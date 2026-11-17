from datetime import datetime

import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from algorithms.go_back_n import GoBackNResult, simulate_go_back_n
from algorithms.sliding_window import SlidingWindowResult, simulate_sliding_window
from modules.network_topology import SERVICE_NODES, build_emergency_topology
from modules.packet_simulation import create_transmission_plan


_SLIDING_WINDOW = "Sliding Window"
_GO_BACK_N = "Go-Back-N ARQ"


def _timeline_figure(result: SlidingWindowResult | GoBackNResult) -> go.Figure:
    figure = go.Figure()
    if isinstance(result, SlidingWindowResult):
        data_rounds = []
        data_sequences = []
        acknowledgements_rounds = []
        acknowledgements_sequences = []
        for batch in result.batches:
            data_rounds.extend([batch.round_number] * len(batch.transmitted))
            data_sequences.extend(batch.transmitted)
            acknowledgements_rounds.extend([batch.round_number + 0.35] * len(batch.acknowledged))
            acknowledgements_sequences.extend(batch.acknowledged)
        figure.add_trace(
            go.Scatter(
                x=data_rounds,
                y=data_sequences,
                mode="markers",
                name="DATA sent",
                marker={"size": 11, "color": "#398eb0", "symbol": "circle"},
                text=[f"DATA packet {sequence}" for sequence in data_sequences],
                hovertemplate="%{text}<br>Round %{x}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=acknowledgements_rounds,
                y=acknowledgements_sequences,
                mode="markers",
                name="ACK received",
                marker={"size": 10, "color": "#41b987", "symbol": "diamond"},
                text=[f"ACK {sequence}" for sequence in acknowledgements_sequences],
                hovertemplate="%{text}<br>Round %{x}<extra></extra>",
            )
        )
        rounds = len(result.batches)
        sequence_limit = result.packet_count
    else:
        traces = {
            "received": {"x": [], "y": [], "text": []},
            "retransmitted": {"x": [], "y": [], "text": []},
            "dropped": {"x": [], "y": [], "text": []},
            "discarded": {"x": [], "y": [], "text": []},
        }
        ack_x = []
        ack_y = []
        ack_text = []
        timeout_x = []
        timeout_y = []
        timeout_text = []
        for round_result in result.rounds:
            for sequence in round_result.transmitted:
                if sequence in round_result.dropped:
                    category = "dropped"
                    description = f"Packet {sequence} lost"
                elif sequence in round_result.discarded:
                    category = "discarded"
                    description = f"Packet {sequence} discarded out of order"
                elif round_result.retransmission:
                    category = "retransmitted"
                    description = f"Packet {sequence} retransmitted and received"
                else:
                    category = "received"
                    description = f"Packet {sequence} received"
                traces[category]["x"].append(round_result.round_number)
                traces[category]["y"].append(sequence)
                traces[category]["text"].append(description)
            ack_x.append(round_result.round_number + 0.35)
            ack_y.append(round_result.cumulative_ack)
            ack_text.append(f"Cumulative ACK {round_result.cumulative_ack}")
            if round_result.timeout:
                timeout_x.append(round_result.round_number + 0.65)
                timeout_y.append(0)
                timeout_text.append("Timeout; retransmit from base")

        styles = {
            "received": ("Received", "#41b987", "circle"),
            "retransmitted": ("Retransmitted", "#38b9d8", "diamond"),
            "dropped": ("Lost", "#d75a5e", "x"),
            "discarded": ("Out of order", "#929ba2", "square"),
        }
        for category, (label, color, symbol) in styles.items():
            points = traces[category]
            figure.add_trace(
                go.Scatter(
                    x=points["x"],
                    y=points["y"],
                    mode="markers",
                    name=label,
                    marker={"size": 11, "color": color, "symbol": symbol},
                    text=points["text"],
                    hovertemplate="%{text}<br>Round %{x}<extra></extra>",
                )
            )
        figure.add_trace(
            go.Scatter(
                x=ack_x,
                y=ack_y,
                mode="markers+text",
                name="Cumulative ACK",
                marker={"size": 10, "color": "#e2a04b", "symbol": "triangle-down"},
                text=ack_text,
                textposition="bottom center",
                hovertemplate="%{text}<br>Round %{x}<extra></extra>",
            )
        )
        figure.add_trace(
            go.Scatter(
                x=timeout_x,
                y=timeout_y,
                mode="markers+text",
                name="Timeout",
                marker={"size": 10, "color": "#d75a5e", "symbol": "x"},
                text=timeout_text,
                textposition="bottom center",
                hovertemplate="%{text}<br>Round %{x}<extra></extra>",
            )
        )
        rounds = len(result.rounds)
        sequence_limit = result.packet_count

    figure.update_layout(
        height=430,
        margin={"l": 25, "r": 18, "t": 38, "b": 35},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        legend={"orientation": "h", "x": 0.02, "y": 1.12},
        hovermode="closest",
        xaxis={
            "title": "Transmission round",
            "range": [0.7, rounds + 1],
            "dtick": 1,
            "gridcolor": "#223342",
        },
        yaxis={
            "title": "Packet sequence number",
            "range": [-0.5, sequence_limit + 1],
            "dtick": 1,
            "gridcolor": "#223342",
        },
    )
    return figure


def _render_round_log(result: SlidingWindowResult | GoBackNResult) -> None:
    with st.expander("Inspect protocol event log"):
        if isinstance(result, SlidingWindowResult):
            for batch in result.batches:
                st.write(
                    f"Round {batch.round_number}: sent {list(batch.transmitted)}; "
                    f"received ACKs {list(batch.acknowledged)}; "
                    f"sender base advanced to {batch.base_after_ack}."
                )
        else:
            for round_result in result.rounds:
                message = (
                    f"Round {round_result.round_number}: sent {list(round_result.transmitted)}; "
                    f"received {list(round_result.received)}; "
                    f"dropped {list(round_result.dropped)}; "
                    f"out-of-order discarded {list(round_result.discarded)}; "
                    f"cumulative ACK {round_result.cumulative_ack}."
                )
                if round_result.timeout:
                    message += (
                        f" Timeout; Go-Back-N retransmits from sequence "
                        f"{round_result.cumulative_ack + 1}."
                    )
                elif round_result.retransmission:
                    message += " Retransmission window acknowledged."
                st.write(message)


def render_reliable_transmission():
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])
    graph = build_emergency_topology(failed_links, failed_nodes)
    service_labels = {node: graph.nodes[node]["label"] for node in SERVICE_NODES}

    st.markdown('<div class="eyebrow">TRANSPORT / RELIABLE DATA TRANSFER</div>', unsafe_allow_html=True)
    st.title("Reliable Data Transmission")
    st.markdown(
        "Compare a basic sliding window with Go-Back-N ARQ. The protocol event timeline "
        "uses packet sequence numbers, acknowledgements, losses, and retransmissions from "
        "the selected simulation."
    )

    with st.container(border=True):
        st.markdown('<div class="card-kicker">PROTOCOL CONFIGURATION · SIMULATION ONLY</div>', unsafe_allow_html=True)
        with st.form("reliable_transmission_form"):
            protocol = st.selectbox(
                "Protocol",
                (_SLIDING_WINDOW, _GO_BACK_N),
                key="reliable_protocol_input",
            )
            sender_col, receiver_col = st.columns(2)
            source = sender_col.selectbox(
                "Sender service",
                SERVICE_NODES,
                format_func=service_labels.get,
                index=1,
                key="reliable_sender_input",
            )
            destination = receiver_col.selectbox(
                "Receiver service",
                SERVICE_NODES,
                format_func=service_labels.get,
                index=3,
                key="reliable_receiver_input",
            )
            packet_col, window_col = st.columns(2)
            packet_count = packet_col.number_input(
                "Packet count",
                min_value=1,
                max_value=32,
                value=8,
                step=1,
                key="reliable_packet_count_input",
            )
            window_size = window_col.number_input(
                "Window size",
                min_value=1,
                max_value=16,
                value=4,
                step=1,
                key="reliable_window_size_input",
            )
            inject_loss = st.checkbox(
                "Inject one data-packet loss (Go-Back-N only)",
                key="reliable_inject_loss_input",
                help="The receiver discards subsequent out-of-order frames and returns a cumulative ACK.",
            )
            loss_sequence = st.number_input(
                "Loss sequence number (1-based)",
                min_value=1,
                max_value=32,
                value=2,
                step=1,
                disabled=not inject_loss,
                key="reliable_loss_sequence_input",
            )
            submitted = st.form_submit_button("Run reliable transmission", type="primary")

    if submitted:
        if source == destination:
            st.error("Choose different sender and receiver services.")
        elif inject_loss and protocol != _GO_BACK_N:
            st.error("Packet loss injection is available only for Go-Back-N ARQ.")
        elif inject_loss and loss_sequence > packet_count:
            st.error("The lost sequence number must not exceed the packet count.")
        else:
            try:
                route_plan = create_transmission_plan(
                    graph,
                    source,
                    destination,
                    "Reliable data frame",
                )
                if protocol == _SLIDING_WINDOW:
                    result = simulate_sliding_window(int(packet_count), int(window_size))
                else:
                    result = simulate_go_back_n(
                        int(packet_count),
                        int(window_size),
                        int(loss_sequence) if inject_loss else None,
                    )
            except nx.NetworkXNoPath:
                st.error("No active route connects these services. Restore a link or router first.")
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state["reliable_transmission_result"] = result
                st.session_state["reliable_transmission_protocol"] = protocol
                st.session_state["reliable_transmission_route"] = route_plan.route
                st.session_state["reliable_transmission_route_delay_ms"] = (
                    route_plan.estimated_delivery_delay_ms
                )
                st.session_state["reliable_transmission_endpoints"] = (source, destination)
                activity = st.session_state.get("recent_activity", [])
                if not isinstance(activity, list):
                    activity = []
                activity.insert(
                    0,
                    f"{datetime.now():%H:%M:%S} · {protocol} simulation: "
                    f"{result.total_acknowledged}/{result.packet_count} packets acknowledged.",
                )
                st.session_state["recent_activity"] = activity[:10]

    result = st.session_state.get("reliable_transmission_result")
    if not isinstance(result, (SlidingWindowResult, GoBackNResult)):
        st.info("Configure the protocol and run a simulation to inspect its packet timeline.")
        return

    protocol = st.session_state["reliable_transmission_protocol"]
    route = st.session_state.get("reliable_transmission_route", ())
    endpoints = st.session_state.get("reliable_transmission_endpoints", ())
    route_is_active = bool(route) and all(
        graph.has_edge(first, second)
        and graph.edges[first, second]["status"] == "active"
        for first, second in zip(route, route[1:])
    )
    if route_is_active and endpoints:
        route_labels = [graph.nodes[node]["short_label"] for node in route]
        st.success(f"Current Dijkstra path: {' → '.join(route_labels)}")
    else:
        st.warning(
            "The saved protocol result remains available, but its route is no longer active. "
            "Restore connectivity and run the simulation again."
        )

    if isinstance(result, SlidingWindowResult):
        retransmissions = 0
        timeouts = 0
        transmission_rounds = len(result.batches)
    else:
        retransmissions = result.retransmission_count
        timeouts = result.timeout_count
        transmission_rounds = len(result.rounds)

    summary = st.columns(5)
    summary[0].metric("Packets acknowledged", f"{result.total_acknowledged}/{result.packet_count}")
    summary[1].metric("Window size", result.window_size)
    summary[2].metric("Transmission rounds", transmission_rounds)
    summary[3].metric("Retransmitted frames", retransmissions)
    summary[4].metric("Timeouts", timeouts)
    st.plotly_chart(
        _timeline_figure(result),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key="reliable_transmission_timeline",
    )
    _render_round_log(result)
    if isinstance(result, GoBackNResult) and result.lost_packet is not None:
        st.warning(
            f"Packet {result.lost_packet} was dropped on its first attempt. Frames after "
            "the missing sequence were discarded until the cumulative ACK timed out."
        )
    st.caption(
        "Protocol outcomes are simulated. The selected Dijkstra path is checked against "
        "the current network topology; this does not send real traffic."
    )


render_reliable_transmission()
