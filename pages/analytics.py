import plotly.graph_objects as go
import streamlit as st

from algorithms.leaky_bucket import (
    LeakyBucketResult,
    compare_leaky_bucket_profiles,
)
from modules.message_transfer import PacketEvent
from modules.performance import summarize_packet_events
from modules.traffic_input import parse_arrivals


_COMPARISON_DEFAULT_ARRIVALS = "2, 8, 2, 7, 1, 8, 1, 6"


def _delivery_figure(events: list[PacketEvent]) -> go.Figure:
    statuses = ("Delivered", "Failed")
    counts = [
        sum(event.status == status for event in events)
        for status in statuses
    ]
    figure = go.Figure(
        go.Bar(
            x=list(statuses),
            y=counts,
            marker_color=["#41b987", "#d75a5e"],
            text=counts,
            textposition="auto",
        )
    )
    figure.update_layout(
        height=320,
        margin={"l": 18, "r": 18, "t": 24, "b": 30},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        xaxis={"title": "Simulated packet outcome"},
        yaxis={"title": "Packets", "rangemode": "tozero", "gridcolor": "#223342"},
    )
    return figure


def _delay_figure(events: list[PacketEvent]) -> go.Figure:
    delivered = [event for event in events if event.transmission_delay_ms is not None]
    figure = go.Figure(
        go.Scatter(
            x=[event.packet_id for event in delivered],
            y=[event.transmission_delay_ms for event in delivered],
            mode="lines+markers",
            name="Estimated DATA/ACK delay",
            line={"color": "#38b9d8", "width": 2},
            marker={"size": 8},
            hovertemplate="%{x}<br>%{y:.2f} ms<extra></extra>",
        )
    )
    figure.update_layout(
        height=320,
        margin={"l": 18, "r": 18, "t": 24, "b": 55},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        xaxis={"title": "Packet ID", "gridcolor": "#223342"},
        yaxis={"title": "Estimated delay (ms)", "gridcolor": "#223342"},
    )
    return figure


def _queue_figure(result: LeakyBucketResult) -> go.Figure:
    ticks = [step.tick for step in result.steps]
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=ticks,
            y=[step.arrivals for step in result.steps],
            mode="lines+markers",
            name="Incoming",
            line={"color": "#398eb0"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=ticks,
            y=[step.transmitted for step in result.steps],
            mode="lines+markers",
            name="Transmitted",
            line={"color": "#41b987"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=ticks,
            y=[step.dropped for step in result.steps],
            mode="lines+markers",
            name="Dropped",
            line={"color": "#d75a5e"},
        )
    )
    figure.add_trace(
        go.Scatter(
            x=ticks,
            y=[step.queued_after_leak for step in result.steps],
            mode="lines+markers",
            name="Queued",
            line={"color": "#e2a04b"},
        )
    )
    figure.update_layout(
        height=340,
        margin={"l": 18, "r": 18, "t": 30, "b": 35},
        paper_bgcolor="#0c1928",
        plot_bgcolor="#0c1928",
        font={"color": "#dce8f1", "family": "Inter, sans-serif"},
        legend={"orientation": "h", "x": 0.02, "y": 1.12},
        xaxis={"title": "Time slot", "dtick": 1, "gridcolor": "#223342"},
        yaxis={"title": "Packets", "rangemode": "tozero", "gridcolor": "#223342"},
    )
    return figure


def _render_profile_comparison() -> None:
    latest = st.session_state.get("leaky_bucket_result")
    default_arrivals = (
        ", ".join(str(step.arrivals) for step in latest.steps)
        if isinstance(latest, LeakyBucketResult)
        else _COMPARISON_DEFAULT_ARRIVALS
    )
    default_capacity = latest.capacity if isinstance(latest, LeakyBucketResult) else 8

    st.markdown(
        '<div class="section-heading">Normal vs congestion-stress comparison</div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(
            '<div class="card-kicker">CONTROLLED QUEUE SIMULATION</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            "Both profiles use the same offered packet arrivals and buffer capacity. "
            "Only the router output service rate changes."
        )
        with st.form("analytics_profile_comparison_form"):
            arrivals_text = st.text_input(
                "Packets arriving in each time slot",
                value=default_arrivals,
                key="analytics_comparison_arrivals",
                help="Enter up to 24 non-negative whole numbers separated by commas.",
            )
            input_col, normal_col, stress_col = st.columns(3)
            capacity = input_col.number_input(
                "Buffer capacity (packets)",
                min_value=1,
                max_value=40,
                value=default_capacity,
                step=1,
                key="analytics_comparison_capacity",
            )
            normal_rate = normal_col.number_input(
                "Normal output rate (packets / slot)",
                min_value=1,
                max_value=40,
                value=4,
                step=1,
                key="analytics_comparison_normal_rate",
            )
            stress_rate = stress_col.number_input(
                "Stress output rate (packets / slot)",
                min_value=1,
                max_value=40,
                value=1,
                step=1,
                key="analytics_comparison_stress_rate",
            )
            submitted = st.form_submit_button(
                "Compare traffic profiles",
                type="primary",
            )

        if submitted:
            st.session_state.pop("analytics_profile_comparison", None)
            try:
                arrivals = parse_arrivals(arrivals_text)
                normal, stress = compare_leaky_bucket_profiles(
                    arrivals,
                    int(capacity),
                    int(normal_rate),
                    int(stress_rate),
                )
            except ValueError as error:
                st.error(f"Comparison not run: {error}")
            else:
                st.session_state["analytics_profile_comparison"] = {
                    "arrivals": tuple(arrivals),
                    "capacity": int(capacity),
                    "normal_rate": int(normal_rate),
                    "stress_rate": int(stress_rate),
                    "normal": normal,
                    "stress": stress,
                }

        comparison = st.session_state.get("analytics_profile_comparison")
        if not isinstance(comparison, dict):
            st.info("Configure the traffic profile and compare the two queue simulations.")
            return

        normal = comparison.get("normal")
        stress = comparison.get("stress")
        arrivals = comparison.get("arrivals")
        if (
            not isinstance(normal, LeakyBucketResult)
            or not isinstance(stress, LeakyBucketResult)
            or not isinstance(arrivals, tuple)
        ):
            st.error("Saved comparison data is invalid. Run the comparison again.")
            return

        st.caption(
            f"Same {len(arrivals)}-slot arrival sequence · buffer "
            f"{comparison['capacity']} packets · normal service "
            f"{comparison['normal_rate']} packets/slot · stress service "
            f"{comparison['stress_rate']} packets/slot."
        )
        normal_col, stress_col = st.columns(2)
        for column, title, result in (
            (normal_col, "Normal service profile", normal),
            (stress_col, "Reduced-service stress profile", stress),
        ):
            with column:
                st.markdown(f"### {title}")
                stats = st.columns(2)
                drop_rate = (
                    100 * result.total_dropped / result.total_arrivals
                    if result.total_arrivals
                    else 0.0
                )
                stats[0].metric("Packets transmitted", result.total_transmitted)
                stats[1].metric("Packets dropped", result.total_dropped)
                stats = st.columns(2)
                stats[0].metric("Packet drop rate", f"{drop_rate:.1f}%")
                stats[1].metric(
                    "Congested slots",
                    f"{result.congested_slots} / {len(result.steps)}",
                )
                st.plotly_chart(
                    _queue_figure(result),
                    width="stretch",
                    config={"displaylogo": False, "responsive": True},
                    key=f"analytics_{title.lower().replace(' ', '_')}_chart",
                )
        st.caption(
            "The Leaky Bucket comparison measures queued, transmitted, and dropped "
            "packets per time slot. It does not estimate link delay or Mbps throughput."
        )


def render_analytics() -> None:
    st.markdown('<div class="eyebrow">OBSERVABILITY / PERFORMANCE</div>', unsafe_allow_html=True)
    st.title("Performance Analytics")
    st.markdown(
        "Metrics are calculated from simulated emergency-message packet records and the "
        "latest Leaky Bucket run. No live network measurements are claimed."
    )

    events = st.session_state.get("packet_events", [])
    if not isinstance(events, list):
        st.error("Packet event state is invalid. Reload the application before continuing.")
        return
    records = [event for event in events if isinstance(event, PacketEvent)]
    summary = summarize_packet_events(records)

    st.markdown('<div class="section-heading">Packet delivery performance</div>', unsafe_allow_html=True)
    metrics = st.columns(5)
    metrics[0].metric("Packets", summary.total_packets)
    metrics[1].metric("Delivered", summary.delivered_packets)
    metrics[2].metric(
        "Delivery ratio",
        f"{summary.packet_delivery_ratio_percent:.1f}%"
        if summary.packet_delivery_ratio_percent is not None
        else "No packet data",
    )
    metrics[3].metric(
        "Average delay",
        f"{summary.average_delay_ms:.2f} ms"
        if summary.average_delay_ms is not None
        else "No delivered packets",
    )
    metrics[4].metric(
        "Modeled throughput",
        f"{summary.modeled_throughput_mbps:.4f} Mbps"
        if summary.modeled_throughput_mbps is not None
        else "No delivered packets",
    )

    if records:
        delivery_col, delay_col = st.columns(2)
        with delivery_col:
            st.plotly_chart(
                _delivery_figure(records),
                width="stretch",
                config={"displaylogo": False},
                key="packet_delivery_analytics",
            )
        with delay_col:
            st.plotly_chart(
                _delay_figure(records),
                width="stretch",
                config={"displaylogo": False},
                key="packet_delay_analytics",
            )
    else:
        st.info("Process a message in Emergency Communication to generate packet analytics.")

    bucket_result = st.session_state.get("leaky_bucket_result")
    if isinstance(bucket_result, LeakyBucketResult):
        st.markdown('<div class="section-heading">Latest congestion simulation</div>', unsafe_allow_html=True)
        queue_metrics = st.columns(4)
        queue_metrics[0].metric("Arrivals", bucket_result.total_arrivals)
        queue_metrics[1].metric("Admitted", bucket_result.total_admitted)
        queue_metrics[2].metric("Transmitted", bucket_result.total_transmitted)
        queue_metrics[3].metric("Dropped", bucket_result.total_dropped)
        st.plotly_chart(
            _queue_figure(bucket_result),
            width="stretch",
            config={"displaylogo": False},
            key="queue_performance_analytics",
        )
    else:
        st.info("Run Leaky Bucket in Congestion Control to add queue analysis.")

    _render_profile_comparison()

    st.caption(
        "Modeled throughput is total delivered payload-plus-header bits divided by the "
        "sum of estimated DATA/ACK delays. It is a simulation estimate, not measured link throughput."
    )


render_analytics()
