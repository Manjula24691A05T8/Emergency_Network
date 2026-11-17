import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from algorithms.distance_vector import (
    DistanceVectorResult,
    get_distance_vector_path,
    simulate_distance_vector,
)
from modules.network_topology import (
    SERVICE_NODES,
    active_network,
    build_emergency_topology,
)


def _link_label(graph: nx.Graph, link: tuple[str, str]) -> str:
    first, second = link
    return f"{graph.nodes[first]['label']} ↔ {graph.nodes[second]['label']}"


def _path_cost(graph: nx.Graph, path: list[str]) -> float:
    return sum(
        float(graph.edges[first, second]["delay_ms"])
        for first, second in zip(path, path[1:])
    )


def _calculate_routes(graph: nx.Graph, source: str, destination: str) -> dict:
    network = active_network(graph)
    distance_vector = simulate_distance_vector(graph)
    try:
        dijkstra_path = nx.dijkstra_path(network, source, destination, weight="delay_ms")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        dijkstra_path = []
    distance_vector_path = get_distance_vector_path(
        distance_vector,
        source,
        destination,
    )
    return {
        "distance_vector": distance_vector,
        "dijkstra_path": dijkstra_path,
        "distance_vector_path": distance_vector_path,
        "dijkstra_cost": _path_cost(graph, dijkstra_path) if dijkstra_path else None,
        "distance_vector_cost": (
            _path_cost(graph, distance_vector_path) if distance_vector_path else None
        ),
    }


def _route_text(graph: nx.Graph, path: list[str]) -> str:
    if not path:
        return "Unavailable"
    return " → ".join(graph.nodes[node]["short_label"] for node in path)


def _render_comparison(graph: nx.Graph, comparison: dict, heading: str) -> None:
    st.markdown(f"### {heading}")
    left, right = st.columns(2)
    with left:
        st.markdown("**Dijkstra**")
        st.write(_route_text(graph, comparison["dijkstra_path"]))
        if comparison["dijkstra_cost"] is not None:
            st.caption(f"Total link delay cost · {comparison['dijkstra_cost']:.2f} ms")
    with right:
        st.markdown("**Distance Vector**")
        st.write(_route_text(graph, comparison["distance_vector_path"]))
        if comparison["distance_vector_cost"] is not None:
            st.caption(
                f"Total link delay cost · "
                f"{comparison['distance_vector_cost']:.2f} ms · "
                f"converged in {comparison['distance_vector'].convergence_round} rounds"
            )
    if not comparison["dijkstra_path"] and not comparison["distance_vector_path"]:
        st.warning("No active route connects the selected services.")
    elif comparison["dijkstra_cost"] != comparison["distance_vector_cost"]:
        st.warning("The algorithms returned different route costs; inspect the active links.")
    else:
        st.success("Both algorithms agree on the minimum active-link delay cost.")


def _convergence_figure(
    result: DistanceVectorResult,
    source: str,
    destination: str,
) -> go.Figure:
    rounds = [snapshot.round_number for snapshot in result.history]
    costs = [
        snapshot.tables[source][destination].cost
        for snapshot in result.history
    ]
    figure = go.Figure(
        go.Scatter(
            x=rounds,
            y=costs,
            mode="lines+markers",
            name="Advertised route cost",
            line={"color": "#38b9d8", "width": 3},
            marker={"size": 8},
            connectgaps=False,
            hovertemplate="Round %{x}<br>Cost %{y:.2f} ms<extra></extra>",
        )
    )
    figure.update_layout(
        height=300,
        margin={"l": 18, "r": 18, "t": 28, "b": 30},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        xaxis={"title": "Exchange round", "dtick": 1, "gridcolor": "#223342"},
        yaxis={"title": "Best-known route cost (ms)", "gridcolor": "#223342"},
    )
    return figure


def _render_routing_table(graph: nx.Graph, result: DistanceVectorResult, source: str) -> None:
    lines = ["Destination | Next hop | Cost (ms)"]
    for destination, entry in result.tables[source].items():
        label = graph.nodes[destination]["short_label"]
        next_hop = (
            graph.nodes[entry.next_hop]["short_label"]
            if entry.next_hop in graph
            else "not available"
        )
        cost = f"{entry.cost:.2f}" if entry.cost is not None else "unreachable"
        lines.append(f"{label} | {next_hop} | {cost}")
    st.code("\n".join(lines), language="text")


def render_routing() -> None:
    failed_links = st.session_state.setdefault("failed_links", [])
    failed_nodes = st.session_state.setdefault("failed_nodes", [])
    graph = build_emergency_topology(failed_links, failed_nodes)
    active_links = [
        (first, second)
        for first, second, data in graph.edges(data=True)
        if data["status"] == "active"
    ]
    service_labels = {node: graph.nodes[node]["label"] for node in SERVICE_NODES}

    st.markdown('<div class="eyebrow">NETWORK LAYER / ROUTING</div>', unsafe_allow_html=True)
    st.title("Routing Algorithms")
    st.markdown(
        "Compare weighted Dijkstra routing with synchronous Distance Vector updates. "
        "Both algorithms use active links and their configured link-delay costs."
    )

    with st.container(border=True):
        st.markdown('<div class="card-kicker">ROUTE COMPARISON · SIMULATION ONLY</div>', unsafe_allow_html=True)
        with st.form("routing_comparison_form"):
            source_col, destination_col = st.columns(2)
            source = source_col.selectbox(
                "Source service",
                SERVICE_NODES,
                format_func=service_labels.get,
                index=1,
                key="routing_source_input",
            )
            destination = destination_col.selectbox(
                "Destination service",
                SERVICE_NODES,
                format_func=service_labels.get,
                index=3,
                key="routing_destination_input",
            )
            preview_failure = st.checkbox(
                "Preview one link failure without changing the shared topology",
                key="routing_preview_failure_input",
            )
            if active_links:
                failed_link = st.selectbox(
                    "Link to remove in preview",
                    active_links,
                    format_func=lambda link: _link_label(graph, link),
                    disabled=not preview_failure,
                    key="routing_failure_link_input",
                )
            else:
                failed_link = None
                st.caption("No active link is available for a failure preview.")
            submitted = st.form_submit_button("Compare routes", type="primary")

    if submitted:
        if source == destination:
            st.error("Choose different source and destination services.")
            st.session_state.pop("routing_comparison", None)
        else:
            try:
                before = _calculate_routes(graph, source, destination)
                after = None
                if preview_failure:
                    if failed_link is None:
                        raise ValueError("No active link is available to fail.")
                    preview_graph = build_emergency_topology(
                        [*failed_links, failed_link],
                        failed_nodes,
                    )
                    after = _calculate_routes(preview_graph, source, destination)
            except ValueError as error:
                st.error(f"Routing comparison not run: {error}")
                st.session_state.pop("routing_comparison", None)
            else:
                st.session_state["routing_comparison"] = {
                    "source": source,
                    "destination": destination,
                    "before": before,
                    "after": after,
                    "failed_link": failed_link if preview_failure else None,
                }

    comparison_state = st.session_state.get("routing_comparison")
    if not isinstance(comparison_state, dict):
        st.info("Select endpoints and compare the current routing tables.")
        return

    source = comparison_state["source"]
    destination = comparison_state["destination"]
    before = comparison_state["before"]
    after = comparison_state["after"]
    _render_comparison(graph, before, "Current topology")

    selected_comparison = before
    selected_graph = graph
    if after is not None:
        failed_link = comparison_state["failed_link"]
        preview_graph = build_emergency_topology([*failed_links, failed_link], failed_nodes)
        st.markdown("---")
        _render_comparison(
            preview_graph,
            after,
            f"After removing {_link_label(graph, failed_link)}",
        )
        selected_comparison = after
        selected_graph = preview_graph
        if before["distance_vector_path"] and after["distance_vector_path"]:
            st.info(
                "The preview changes only this routing calculation. Use Network Topology "
                "to apply or restore failures in the shared simulation."
            )

    result = selected_comparison["distance_vector"]
    if source in result.tables and destination in result.tables[source]:
        st.markdown('<div class="section-heading">Distance Vector convergence</div>', unsafe_allow_html=True)
        convergence, table = st.columns([1.35, 1])
        with convergence:
            st.plotly_chart(
                _convergence_figure(result, source, destination),
                width="stretch",
                config={"displaylogo": False},
                key="distance_vector_convergence",
            )
        with table:
            st.markdown(
                f"**Final routing table at {selected_graph.nodes[source]['short_label']}**"
            )
            _render_routing_table(selected_graph, result, source)
        st.caption(
            f"Each round exchanges the previous round's known costs. "
            f"Convergence confirmed after {result.convergence_round} rounds; "
            "unreachable routes are shown explicitly."
        )

    st.caption(
        "Link cost is the configured one-way propagation delay in milliseconds. "
        "Dijkstra and Distance Vector run locally on the active simulated topology."
    )


render_routing()
