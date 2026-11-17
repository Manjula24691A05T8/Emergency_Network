import streamlit as st

from modules.network_topology import (
    ROUTER_NODES,
    SERVICE_NODES,
    build_emergency_topology,
    build_topology_figure,
    canonical_link,
    get_available_paths,
    get_topology_metrics,
)


def _link_label(graph, link):
    first, second = link
    return f"{graph.nodes[first]['label']}  ↔  {graph.nodes[second]['label']}"


def render_topology():
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])
    graph = build_emergency_topology(failed_links, failed_nodes)
    metrics = get_topology_metrics(graph)

    st.markdown('<div class="eyebrow">INFRASTRUCTURE / LIVE TOPOLOGY</div>', unsafe_allow_html=True)
    st.title("Emergency Network Topology")
    st.markdown(
        "A redundant, two-router core connects emergency command, public-safety, "
        "medical, rescue, and shelter services. Link properties are simulated."
    )

    notice = st.session_state.pop("topology_notice", None)
    if notice:
        st.success(notice)

    summary = st.columns(4)
    summary[0].metric("Network nodes", metrics["total_nodes"])
    summary[1].metric("Routers / switches", f"{metrics['active_routers']} / {metrics['active_switches']}")
    summary[2].metric("Active connections", metrics["active_connections"])
    summary[3].metric("Network health", metrics["network_health"])

    control_col, path_col = st.columns([1, 1])
    with control_col:
        with st.container(border=True):
            st.markdown('<div class="card-kicker">LINK CONTROL</div>', unsafe_allow_html=True)
            links = list(graph.edges)
            selected_link = st.selectbox(
                "Select a connection",
                links,
                format_func=lambda link: _link_label(graph, link),
                key="topology_selected_link",
            )
            status = graph.edges[selected_link]["status"]
            st.caption(
                f"{status.title()} · "
                f"{graph.edges[selected_link]['bandwidth_mbps']:,} Mbps · "
                f"{graph.edges[selected_link]['delay_ms']:.1f} ms"
            )
            endpoint_failed = any(node in failed_nodes for node in selected_link)
            if endpoint_failed:
                st.caption("Unavailable because an attached router is failed; restore that router first.")

            fail_col, restore_col = st.columns(2)
            if fail_col.button(
                "Fail selected link",
                disabled=status == "failed",
                width="stretch",
                type="primary",
            ):
                failed = {canonical_link(*link) for link in failed_links}
                failed.add(canonical_link(*selected_link))
                st.session_state["failed_links"] = sorted(failed)
                st.session_state["topology_notice"] = (
                    f"Simulated failure: {_link_label(graph, selected_link)}."
                )
                st.rerun()

            if restore_col.button(
                "Restore selected",
                disabled=status == "active" or endpoint_failed,
                width="stretch",
            ):
                failed = {canonical_link(*link) for link in failed_links}
                failed.discard(canonical_link(*selected_link))
                st.session_state["failed_links"] = sorted(failed)
                st.session_state["topology_notice"] = (
                    f"Restored connection: {_link_label(graph, selected_link)}."
                )
                st.rerun()

            st.markdown("**Router control**")
            selected_router = st.selectbox(
                "Select a router",
                ROUTER_NODES,
                format_func=lambda node: graph.nodes[node]["label"],
                key="topology_selected_router",
            )
            router_failed = graph.nodes[selected_router]["status"] == "failed"
            st.caption("FAILED · traffic cannot transit this router." if router_failed else "ACTIVE")
            router_fail_col, router_restore_col = st.columns(2)
            if router_fail_col.button(
                "Fail selected router",
                disabled=router_failed,
                width="stretch",
                key="topology_fail_router",
            ):
                failed = set(failed_nodes)
                failed.add(selected_router)
                st.session_state["failed_nodes"] = sorted(failed)
                st.session_state["topology_notice"] = (
                    f"Simulated router failure: {graph.nodes[selected_router]['label']}."
                )
                st.rerun()

            if router_restore_col.button(
                "Restore router",
                disabled=not router_failed,
                width="stretch",
                key="topology_restore_router",
            ):
                failed = set(failed_nodes)
                failed.discard(selected_router)
                st.session_state["failed_nodes"] = sorted(failed)
                st.session_state["topology_notice"] = (
                    f"Restored router: {graph.nodes[selected_router]['label']}."
                )
                st.rerun()

            if st.button(
                "Restore all failures",
                disabled=not failed_links and not failed_nodes,
                width="stretch",
                key="topology_restore_all_failures",
            ):
                st.session_state["failed_links"] = []
                st.session_state["failed_nodes"] = []
                st.session_state["topology_notice"] = (
                    "All simulated router and link failures have been restored."
                )
                st.rerun()
            st.caption("Failures affect this browser session only; no real network devices are contacted.")

    with path_col:
        with st.container(border=True):
            st.markdown('<div class="card-kicker">CONNECTIVITY PREVIEW</div>', unsafe_allow_html=True)
            service_labels = {
                node: graph.nodes[node]["label"]
                for node in SERVICE_NODES
            }
            source_col, destination_col = st.columns(2)
            source = source_col.selectbox(
                "Source service",
                SERVICE_NODES,
                format_func=service_labels.get,
                key="topology_source",
            )
            destination = destination_col.selectbox(
                "Destination service",
                SERVICE_NODES,
                index=3,
                format_func=service_labels.get,
                key="topology_destination",
            )
            paths = get_available_paths(graph, source, destination)
            highlighted_links = {
                canonical_link(first, second)
                for path in paths
                for first, second in zip(path, path[1:])
            }
            if source == destination:
                st.info("Select two different services to inspect connectivity.")
            elif paths:
                st.success(
                    f"Showing {len(paths)} active path(s); available paths are highlighted in green."
                )
                with st.expander("Inspect available paths"):
                    for number, path in enumerate(paths, start=1):
                        labels = [graph.nodes[node]["short_label"] for node in path]
                        st.write(f"{number}. " + " → ".join(labels))
            else:
                st.error("No active path connects these services.")
            st.caption(
                "Unweighted connectivity preview; route-cost selection is implemented in Stage 3."
            )

    figure = build_topology_figure(graph, highlighted_links)
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key="emergency_topology_plot",
    )
    st.caption(
        "Hover over a device or link for details. Drag to pan and use the scroll wheel "
        "to zoom. Green links belong to currently available paths."
    )

    with st.expander("Connection inventory"):
        for first, second, data in graph.edges(data=True):
            columns = st.columns([3, 1, 1, 1])
            columns[0].write(_link_label(graph, (first, second)))
            columns[1].write(data["status"].upper())
            columns[2].write(f"{data['bandwidth_mbps']:,} Mbps")
            columns[3].write(f"{data['delay_ms']:.1f} ms")

    if metrics["failed_connections"]:
        failed_routers = sum(
            graph.nodes[node]["status"] == "failed" for node in ROUTER_NODES
        )
        st.warning(
            f"{failed_routers} router(s) failed; "
            f"{metrics['failed_connections']} connection(s) unavailable; "
            f"{metrics['reachable_services']} of {metrics['total_services']} "
            "emergency services remain connected to the control center."
        )


render_topology()
