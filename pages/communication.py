from datetime import datetime

import streamlit as st

from modules.message_transfer import (
    PRIORITIES,
    EmergencyMessage,
    PacketEvent,
    enqueue_message,
    order_messages,
    process_message,
)
from modules.network_topology import SERVICE_NODES, build_emergency_topology


def _render_queue(queue: list[EmergencyMessage], graph) -> None:
    if not queue:
        st.info("The priority queue is empty.")
        return
    lines = ["ID | Priority | Sender → receiver | Message"]
    lines.extend(
        f"{message.message_id} | {message.priority} | "
        f"{graph.nodes[message.source]['short_label']} → "
        f"{graph.nodes[message.destination]['short_label']} | "
        f"{message.content.replace('|', '/').replace(chr(10), ' ')[:48]}"
        for message in queue
    )
    st.code("\n".join(lines), language="text")


def render_communication() -> None:
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])
    graph = build_emergency_topology(failed_links, failed_nodes)
    labels = {node: graph.nodes[node]["label"] for node in SERVICE_NODES}
    st.session_state.setdefault("emergency_message_queue", [])
    st.session_state.setdefault("packet_events", [])
    st.session_state.setdefault("emergency_message_sequence", 0)

    st.markdown('<div class="eyebrow">DISPATCH / PRIORITY COMMUNICATION</div>', unsafe_allow_html=True)
    st.title("Emergency Communication")
    st.markdown(
        "Queue simulated service messages by urgency. The scheduler processes Critical "
        "before High, Medium, and Normal, using FIFO order within each priority."
    )

    with st.container(border=True):
        st.markdown('<div class="card-kicker">MESSAGE COMPOSER · SIMULATION ONLY</div>', unsafe_allow_html=True)
        with st.form("emergency_message_form"):
            sender_col, receiver_col = st.columns(2)
            source = sender_col.selectbox(
                "Sender service",
                SERVICE_NODES,
                format_func=labels.get,
                index=1,
                key="emergency_sender_input",
            )
            destination = receiver_col.selectbox(
                "Receiver service",
                SERVICE_NODES,
                format_func=labels.get,
                index=3,
                key="emergency_receiver_input",
            )
            content = st.text_area(
                "Emergency message",
                max_chars=500,
                key="emergency_message_content_input",
            )
            priority = st.selectbox(
                "Priority",
                PRIORITIES,
                key="emergency_message_priority_input",
            )
            submitted = st.form_submit_button("Queue message", type="primary")

    if submitted:
        try:
            sequence = st.session_state["emergency_message_sequence"] + 1
            message = EmergencyMessage(
                message_id=f"MSG-{sequence:04d}",
                sequence=sequence,
                source=source,
                destination=destination,
                content=content,
                priority=priority,
                queued_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            )
            queue = enqueue_message(st.session_state["emergency_message_queue"], message)
        except ValueError as error:
            st.error(f"Message not queued: {error}")
        else:
            st.session_state["emergency_message_sequence"] = sequence
            st.session_state["emergency_message_queue"] = queue
            activity = st.session_state.get("recent_activity", [])
            if not isinstance(activity, list):
                activity = []
            activity.insert(
                0,
                f"{message.priority} message {message.message_id} queued: "
                f"{graph.nodes[source]['short_label']} → "
                f"{graph.nodes[destination]['short_label']}.",
            )
            st.session_state["recent_activity"] = activity[:10]
            st.success(f"{message.message_id} added to the priority queue.")

    queue = order_messages(st.session_state["emergency_message_queue"])
    st.session_state["emergency_message_queue"] = queue
    st.markdown('<div class="section-heading">Priority queue</div>', unsafe_allow_html=True)
    _render_queue(queue, graph)

    if st.button(
        "Process highest-priority message",
        type="primary",
        disabled=not queue,
        key="process_highest_priority_message",
    ):
        message = queue[0]
        event = process_message(graph, message)
        st.session_state["emergency_message_queue"] = queue[1:]
        packet_events = st.session_state["packet_events"]
        packet_events.insert(0, event)
        st.session_state["packet_events"] = packet_events[:500]
        activity = st.session_state.get("recent_activity", [])
        if not isinstance(activity, list):
            activity = []
        activity.insert(
            0,
            f"{event.timestamp[11:19]} · {message.priority} message "
            f"{message.message_id}: {event.status.lower()}.",
        )
        st.session_state["recent_activity"] = activity[:10]
        if event.status == "Delivered":
            route = " → ".join(graph.nodes[node]["short_label"] for node in event.route)
            st.success(
                f"{message.message_id} delivered over {route}; estimated DATA/ACK "
                f"delay {event.transmission_delay_ms:.2f} ms."
            )
        else:
            st.error(f"{message.message_id} failed: no active route is available.")

    st.caption(
        "Each processed message creates one simulated DATA/ACK packet record. "
        "This page does not contact real emergency services."
    )


render_communication()
