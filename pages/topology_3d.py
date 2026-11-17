from datetime import datetime
from time import perf_counter

import networkx as nx
import streamlit as st

from modules.network_topology import (
    ROUTER_NODES,
    active_network,
    build_emergency_topology,
    canonical_link,
    get_topology_metrics,
)
from algorithms.leaky_bucket import LeakyBucketResult
from modules.packet_simulation import create_transmission_plan
from modules.topology_3d import (
    add_packet_animation,
    add_router_queue_visualization,
    build_3d_topology_figure,
)


def _link_label(graph, link):
    first, second = link
    return f"{graph.nodes[first]['label']}  ↔  {graph.nodes[second]['label']}"


def _route_for_request(graph, request):
    if not isinstance(request, dict):
        return None
    try:
        plan = create_transmission_plan(
            graph,
            request["source"],
            request["destination"],
            request["message"],
            request["inject_packet_loss"],
        )
    except nx.NetworkXNoPath:
        return None
    return list(plan.route)


def _apply_failure_state(
    graph,
    transmission_plan,
    action,
    target,
    failed_links,
    failed_nodes,
):
    request = st.session_state.get("packet_transmission_request")
    before_route = (
        list(transmission_plan.route)
        if transmission_plan is not None
        else _route_for_request(graph, request)
    )
    next_graph = build_emergency_topology(failed_links, failed_nodes)
    started = perf_counter()
    after_route = _route_for_request(next_graph, request)
    route_calculation_ms = (perf_counter() - started) * 1_000

    st.session_state["failed_links"] = list(failed_links)
    st.session_state["failed_nodes"] = list(failed_nodes)
    st.session_state["last_failure_event"] = {
        "action": action,
        "target": target,
        "before_route": before_route,
        "after_route": after_route,
        "has_request": isinstance(request, dict),
        "route_calculation_ms": route_calculation_ms,
    }
    st.rerun()


def _render_failure_controls(graph, transmission_plan):
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])

    st.markdown('<div class="section-heading">Failure and route recovery</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="card-kicker">SIMULATED FAILURE CONTROL</div>', unsafe_allow_html=True)
        st.caption(
            "Fail or restore a topology element. A prepared DATA/ACK exchange is "
            "recomputed over active links and its 3D route animation follows the new path."
        )
        failure_kind = st.radio(
            "Failure target",
            ("Link", "Router"),
            horizontal=True,
            key="3d_failure_target_kind",
        )
        if failure_kind == "Link":
            selected_link = st.selectbox(
                "Select a connection",
                list(graph.edges),
                format_func=lambda link: _link_label(graph, link),
                key="3d_failure_selected_link",
            )
            status = graph.edges[selected_link]["status"]
            endpoint_failed = any(node in failed_nodes for node in selected_link)
            st.caption(
                f"{status.title()} · {graph.edges[selected_link]['bandwidth_mbps']:,} Mbps · "
                f"{graph.edges[selected_link]['delay_ms']:.1f} ms"
            )
            if endpoint_failed:
                st.caption("Unavailable because an attached router is failed; restore that router first.")
            fail_col, restore_col = st.columns(2)
            if fail_col.button(
                "Fail selected link",
                disabled=status == "failed",
                width="stretch",
                type="primary",
                key="3d_fail_selected_link",
            ):
                next_links = {canonical_link(*link) for link in failed_links}
                next_links.add(canonical_link(*selected_link))
                _apply_failure_state(
                    graph,
                    transmission_plan,
                    "failed",
                    _link_label(graph, selected_link),
                    sorted(next_links),
                    list(failed_nodes),
                )
            if restore_col.button(
                "Restore selected link",
                disabled=status == "active" or endpoint_failed,
                width="stretch",
                key="3d_restore_selected_link",
            ):
                next_links = {canonical_link(*link) for link in failed_links}
                next_links.discard(canonical_link(*selected_link))
                _apply_failure_state(
                    graph,
                    transmission_plan,
                    "restored",
                    _link_label(graph, selected_link),
                    sorted(next_links),
                    list(failed_nodes),
                )
        else:
            selected_router = st.selectbox(
                "Select a router",
                ROUTER_NODES,
                format_func=lambda node: graph.nodes[node]["label"],
                key="3d_failure_selected_router",
            )
            router_failed = graph.nodes[selected_router]["status"] == "failed"
            st.caption("FAILED · traffic cannot transit this router." if router_failed else "ACTIVE")
            fail_col, restore_col = st.columns(2)
            if fail_col.button(
                "Fail selected router",
                disabled=router_failed,
                width="stretch",
                type="primary",
                key="3d_fail_selected_router",
            ):
                next_nodes = set(failed_nodes)
                next_nodes.add(selected_router)
                _apply_failure_state(
                    graph,
                    transmission_plan,
                    "failed",
                    graph.nodes[selected_router]["label"],
                    list(failed_links),
                    sorted(next_nodes),
                )
            if restore_col.button(
                "Restore selected router",
                disabled=not router_failed,
                width="stretch",
                key="3d_restore_selected_router",
            ):
                next_nodes = set(failed_nodes)
                next_nodes.discard(selected_router)
                _apply_failure_state(
                    graph,
                    transmission_plan,
                    "restored",
                    graph.nodes[selected_router]["label"],
                    list(failed_links),
                    sorted(next_nodes),
                )

        if st.button(
            "Restore all failures",
            disabled=not failed_links and not failed_nodes,
            width="stretch",
            key="3d_restore_all_failures",
        ):
            _apply_failure_state(
                graph,
                transmission_plan,
                "restored",
                "All links and routers",
                [],
                [],
            )

    event = st.session_state.get("last_failure_event")
    if not isinstance(event, dict):
        return

    with st.container(border=True):
        st.markdown('<div class="card-kicker">ROUTE RECOVERY STATUS</div>', unsafe_allow_html=True)
        st.write(f"**{event['target']} {event['action']}**")
        if not event["has_request"]:
            st.info(
                "Topology state updated. Prepare a DATA/ACK exchange above to compare "
                "the route before and after a failure."
            )
        elif event["after_route"] is None:
            st.error(
                "No active route reaches the prepared destination. Packet animation is "
                "withheld until a path is restored or another endpoint is selected."
            )
        else:
            before_route = event["before_route"]
            after_route = event["after_route"]
            if event["action"] == "restored" and before_route is None:
                st.success("Dijkstra found a route after the failed element was restored.")
            elif before_route != after_route:
                st.success("Dijkstra selected an alternate active route for the prepared exchange.")
            else:
                st.info("The prepared route remains available; this change did not alter its path.")
            route_columns = st.columns(2)
            route_columns[0].write("**Before**")
            route_columns[0].write(
                " → ".join(graph.nodes[node]["short_label"] for node in before_route)
                if before_route
                else "Unavailable"
            )
            route_columns[1].write("**After**")
            route_columns[1].write(
                " → ".join(graph.nodes[node]["short_label"] for node in after_route)
            )
            st.metric(
                "Dijkstra recomputation",
                f"{event['route_calculation_ms']:.3f} ms",
            )
            st.caption(
                "Local route-calculation time only; it does not represent real device "
                "failure detection or routing-protocol convergence."
            )


def _device_profile(node):
    if node["kind"] == "router":
        return "Enterprise rack-mounted router"
    if node["kind"] == "switch":
        return "Managed access switch"
    if node["role"] == "Command and dispatch":
        return "Emergency control facility with server rack"
    return "Emergency service facility"


def _render_packet_transmission(graph):
    st.markdown('<div class="section-heading">Route-based packet transmission</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown('<div class="card-kicker">SIMULATED DATA / ACK EXCHANGE</div>', unsafe_allow_html=True)
        node_ids = list(graph.nodes)
        with st.form("packet_transmission_form"):
            sender_col, receiver_col = st.columns(2)
            with sender_col:
                source = st.selectbox(
                    "Sender",
                    node_ids,
                    index=node_ids.index("police_station"),
                    format_func=lambda node_id: graph.nodes[node_id]["label"],
                    key="packet_sender",
                )
            with receiver_col:
                destination = st.selectbox(
                    "Receiver",
                    node_ids,
                    index=node_ids.index("ambulance_service"),
                    format_func=lambda node_id: graph.nodes[node_id]["label"],
                    key="packet_receiver",
                )
            message = st.text_area(
                "Emergency message",
                value="Request backup at the west sector.",
                max_chars=500,
                key="packet_message",
            )
            inject_packet_loss = st.checkbox(
                "Inject one dropped packet to demonstrate a retry",
                key="inject_packet_loss",
                help="Deterministically drops the first attempt mid-link, then animates one retransmission.",
            )
            submitted = st.form_submit_button("Prepare transmission", type="primary")

    if submitted:
        if source == destination:
            st.session_state.pop("packet_transmission_request", None)
            st.error("Choose different sender and receiver devices.")
        elif not message.strip():
            st.session_state.pop("packet_transmission_request", None)
            st.error("Enter a message before preparing a transmission.")
        else:
            st.session_state["packet_transmission_request"] = {
                "source": source,
                "destination": destination,
                "message": message,
                "inject_packet_loss": inject_packet_loss,
            }
            st.session_state.pop("last_failure_event", None)

    request = st.session_state.get("packet_transmission_request")
    if not isinstance(request, dict):
        return None

    try:
        plan = create_transmission_plan(
            graph,
            request["source"],
            request["destination"],
            request["message"],
            request["inject_packet_loss"],
        )
    except nx.NetworkXNoPath:
        st.error(
            "No active route connects these devices. Restore a link or choose another "
            "sender/receiver pair, then prepare the transmission again."
        )
        return None
    except ValueError as error:
        st.error(str(error))
        return None

    route_labels = [graph.nodes[node_id]["label"] for node_id in plan.route]
    st.success("Dijkstra found an active route. The DATA and ACK animation is ready.")
    route_col, metrics_col = st.columns([1.5, 1])
    with route_col:
        st.write("**Selected route**")
        st.write(" → ".join(route_labels))
        st.caption(
            "The route minimizes per-link delay plus packet serialization time. "
            "Only links currently marked active are considered."
        )
    with metrics_col:
        delay_col, ack_col, total_col, retry_col = st.columns(4)
        delay_col.metric("DATA one-way", f"{plan.one_way_delay_ms:.2f} ms")
        ack_col.metric("ACK return", f"{plan.acknowledgement_delay_ms:.2f} ms")
        total_col.metric("Est. delivery", f"{plan.estimated_delivery_delay_ms:.2f} ms")
        retry_col.metric("Retries", plan.retransmissions)
    st.text(f"Simulated payload: {plan.message}")
    if st.session_state.get("reduced_motion", False):
        st.info(
            "Reduced motion is enabled: the route, delivered DATA/ACK, and any injected "
            "drop are shown as static markers. No animation frames are generated."
        )
    else:
        st.info(
            "Use **Play transmission** in the 3D chart to animate packets along this route. "
            "This is a local simulation; no real emergency message is transmitted."
        )
    if plan.retransmissions:
        st.warning(
            "A first-attempt packet drop is injected mid-link. Playback shows the drop, "
            "one retransmission, delivery, and the returning acknowledgement."
        )
    if submitted:
        activity = st.session_state.get("recent_activity", [])
        if not isinstance(activity, list):
            activity = []
        activity.insert(
            0,
            f"{datetime.now():%H:%M:%S} · Prepared simulated DATA/ACK exchange: "
            f"{graph.nodes[plan.source]['label']} → {graph.nodes[plan.destination]['label']}",
        )
        st.session_state["recent_activity"] = activity[:10]
    return plan


def render_3d_topology():
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])
    graph = build_emergency_topology(failed_links, failed_nodes)
    metrics = get_topology_metrics(graph)
    active_graph = active_network(graph)
    reachable = (
        set()
        if "control_center" not in active_graph
        else nx.node_connected_component(active_graph, "control_center")
    )

    st.markdown('<div class="eyebrow">INFRASTRUCTURE / PHYSICAL VIEW</div>', unsafe_allow_html=True)
    st.title("3D Network Infrastructure")
    st.markdown(
        "Interactive hardware-scale scene built from the current simulated topology. "
        "Rotate to inspect the facilities, racks, network devices, and physical links."
    )

    summary = st.columns(4)
    summary[0].metric("Devices and facilities", metrics["total_nodes"])
    summary[1].metric("Routers / switches", f"{metrics['active_routers']} / {metrics['active_switches']}")
    summary[2].metric("Active / failed links", f"{metrics['active_connections']} / {metrics['failed_connections']}")
    summary[3].metric("Network health", metrics["network_health"])

    transmission_plan = _render_packet_transmission(graph)
    _render_failure_controls(graph, transmission_plan)
    node_ids = list(graph.nodes)
    control_col, state_col = st.columns([2, 1])
    with control_col:
        selected_id = st.selectbox(
            "Inspect device or facility",
            node_ids,
            format_func=lambda node_id: graph.nodes[node_id]["label"],
            key="selected_3d_device",
        )
    with state_col:
        reduced_detail = st.toggle(
            "Reduced-detail mode",
            value=False,
            key="reduced_3d_detail",
            help="Uses fewer rack details and omits the floor grid to reduce rendering work.",
        )

    figure = build_3d_topology_figure(graph, reduced_detail=reduced_detail)
    if transmission_plan is not None:
        figure = add_packet_animation(
            figure,
            graph,
            transmission_plan.route,
            inject_packet_loss=bool(transmission_plan.retransmissions),
            reduced_motion=bool(st.session_state.get("reduced_motion", False)),
        )
    queue_snapshot_message = None
    queue_result = st.session_state.get("leaky_bucket_result")
    queue_router = st.session_state.get("leaky_bucket_router")
    if isinstance(queue_result, LeakyBucketResult):
        if queue_router in graph and graph.nodes[queue_router]["status"] == "active":
            selected_tick = st.session_state.get("leaky_bucket_selected_tick", 1)
            if not isinstance(selected_tick, int) or isinstance(selected_tick, bool):
                selected_tick = 1
            step_index = min(max(selected_tick - 1, 0), len(queue_result.steps) - 1)
            queue_step = queue_result.steps[step_index]
            figure = add_router_queue_visualization(
                figure,
                graph,
                queue_router,
                occupancy=queue_step.queued_before_leak,
                capacity=queue_result.capacity,
                tick=queue_step.tick,
            )
            queue_snapshot_message = (
                f"Router queue snapshot · {graph.nodes[queue_router]['short_label']} · "
                f"slot {queue_step.tick} · {queue_step.queued_before_leak}/"
                f"{queue_result.capacity} packets before output service."
            )
        else:
            queue_snapshot_message = (
                "The saved queue belongs to a failed router; run congestion simulation "
                "on an active router to display its buffer."
            )
    st.plotly_chart(
        figure,
        width="stretch",
        config={
            "displaylogo": False,
            "scrollZoom": True,
            "responsive": True,
        },
        key="physical_topology_3d",
    )
    st.caption(
        "Drag to orbit, scroll to zoom, and hover over cables or device labels for details. "
        "Red dashed cables and red X device markers are unavailable. The highlighted route "
        "and packet markers follow the selected Dijkstra transmission."
    )
    if queue_snapshot_message is not None:
        if queue_router in graph and graph.nodes[queue_router]["status"] == "active":
            st.info(queue_snapshot_message)
        else:
            st.warning(queue_snapshot_message)
        st.caption(
            "Open **Congestion Control** from the sidebar to adjust the Leaky Bucket "
            "and selected time slot."
        )

    selected = graph.nodes[selected_id]
    selected_status = "Failed" if selected["status"] == "failed" else "Active"
    with st.container(border=True):
        device_col, links_col = st.columns([1, 1])
        with device_col:
            st.markdown('<div class="card-kicker">DEVICE INSPECTOR</div>', unsafe_allow_html=True)
            st.markdown(f"### {selected['label']}")
            st.caption(_device_profile(selected))
            st.metric("Device status", selected_status)
            st.caption(
                "Reachable from control center"
                if selected_id in reachable
                else "Isolated from control center"
            )
            st.write(f"**Role:** {selected['role']}")
            st.write(f"**Simulated IP:** `{selected['address']}`")

        with links_col:
            st.markdown('<div class="card-kicker">ATTACHED LINKS</div>', unsafe_allow_html=True)
            for _, neighbor, edge_data in graph.edges(selected_id, data=True):
                st.caption(
                    f"{graph.nodes[neighbor]['label']} · {edge_data['status'].upper()} · "
                    f"{edge_data['bandwidth_mbps']:,} Mbps · {edge_data['delay_ms']:.1f} ms"
                )

    with st.expander("Model and simulation notes"):
        st.markdown(
            "- Emergency buildings, rack cabinets, router chassis, switch ports, and the rescue-site communications tower are generated as 3D meshes.\n"
            "- Cable status and link hover data are taken from the NetworkX graph; a failed topology link is rendered as unavailable.\n"
            "- The tower is a facility asset, not an additional routing node.\n"
            "- Geometry is an engineering visualization, not manufacturer-specific CAD. Plotly provides interactive 3D lighting but not full PBR materials or shadow maps."
        )
        st.caption(
            "Three.js is not installed locally. This view uses the existing Plotly renderer "
            "and makes no external CDN requests."
        )


render_3d_topology()
