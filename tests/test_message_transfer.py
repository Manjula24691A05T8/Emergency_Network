import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from modules.message_transfer import (
    EmergencyMessage,
    enqueue_message,
    process_message,
)
from modules.network_topology import build_emergency_topology
from modules.performance import summarize_packet_events
from algorithms.leaky_bucket import simulate_leaky_bucket


COMMUNICATION_PAGE = str(
    Path(__file__).resolve().parents[1] / "pages" / "communication.py"
)
PACKET_MONITOR_PAGE = str(
    Path(__file__).resolve().parents[1] / "pages" / "packet_monitor.py"
)
ANALYTICS_PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "analytics.py")


def _message(sequence: int, priority: str) -> EmergencyMessage:
    return EmergencyMessage(
        message_id=f"MSG-{sequence:04d}",
        sequence=sequence,
        source="police_station",
        destination="ambulance_service",
        content=f"Emergency {sequence}",
        priority=priority,
        queued_at="2026-01-01T00:00:00+00:00",
    )


class MessageTransferTests(unittest.TestCase):
    def test_priority_queue_sorts_urgency_then_preserves_fifo_order(self):
        queue = enqueue_message(
            [_message(1, "Normal"), _message(3, "Critical"), _message(2, "High")],
            _message(4, "Critical"),
        )

        self.assertEqual(
            [(message.sequence, message.priority) for message in queue],
            [(3, "Critical"), (4, "Critical"), (2, "High"), (1, "Normal")],
        )

    def test_processing_uses_active_dijkstra_route_and_records_packet_metadata(self):
        graph = build_emergency_topology([("switch_north", "router_a")])

        event = process_message(graph, _message(1, "Critical"))

        self.assertEqual(event.status, "Delivered")
        self.assertEqual(event.source_ip, graph.nodes["police_station"]["address"])
        self.assertEqual(
            event.destination_ip,
            graph.nodes["ambulance_service"]["address"],
        )
        self.assertNotIn(
            ("switch_north", "router_a"),
            list(zip(event.route, event.route[1:])),
        )
        self.assertGreater(event.transmission_delay_ms, 0)

    def test_unreachable_message_is_recorded_as_failed(self):
        graph = build_emergency_topology(
            [
                ("switch_north", "router_a"),
                ("switch_north", "router_b"),
            ]
        )

        event = process_message(graph, _message(1, "High"))

        self.assertEqual(event.status, "Failed: no active route")
        self.assertIsNone(event.transmission_delay_ms)
        self.assertEqual(event.route, ())

    def test_performance_summary_reports_delivery_loss_delay_and_throughput(self):
        graph = build_emergency_topology()
        delivered = process_message(graph, _message(1, "High"))
        failed = process_message(
            build_emergency_topology(
                [
                    ("switch_north", "router_a"),
                    ("switch_north", "router_b"),
                ]
            ),
            _message(2, "Normal"),
        )

        summary = summarize_packet_events([delivered, failed])

        self.assertEqual(summary.total_packets, 2)
        self.assertEqual(summary.delivered_packets, 1)
        self.assertEqual(summary.failed_packets, 1)
        self.assertEqual(summary.packet_delivery_ratio_percent, 50)
        self.assertEqual(summary.packet_loss_ratio_percent, 50)
        self.assertGreater(summary.average_delay_ms, 0)
        self.assertGreater(summary.modeled_throughput_mbps, 0)

    def test_communication_page_queues_message(self):
        app = AppTest.from_file(COMMUNICATION_PAGE).run()
        app.text_area[0].set_value("Need medical support.")
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state["emergency_message_queue"]), 1)

    def test_communication_page_processes_highest_priority_message(self):
        app = AppTest.from_file(COMMUNICATION_PAGE)
        app.session_state["emergency_message_queue"] = [
            _message(1, "Normal"),
            _message(2, "Critical"),
        ]
        app.session_state["emergency_message_sequence"] = 2
        app.run()
        process_button = next(
            button
            for button in app.button
            if button.label == "Process highest-priority message"
        )
        process_button.click().run()

        self.assertFalse(app.exception)
        self.assertEqual(
            [message.sequence for message in app.session_state["emergency_message_queue"]],
            [1],
        )
        self.assertEqual(len(app.session_state["packet_events"]), 1)
        self.assertEqual(app.session_state["packet_events"][0].packet_id, "PKT-000002")
        self.assertEqual(app.session_state["packet_events"][0].status, "Delivered")

    def test_packet_monitor_renders_saved_packet_records(self):
        event = process_message(build_emergency_topology(), _message(1, "Critical"))
        app = AppTest.from_file(PACKET_MONITOR_PAGE)
        app.session_state["packet_events"] = [event]
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Recorded packets"], "1")
        self.assertEqual(metrics["Delivered"], "1")
        self.assertEqual(len(app.code), 1)

    def test_packet_monitor_explains_wireshark_separation_when_empty(self):
        app = AppTest.from_file(PACKET_MONITOR_PAGE).run()

        self.assertFalse(app.exception)
        self.assertEqual(len(app.expander), 1)
        self.assertIn("Wireshark", app.expander[0].label)

    def test_packet_monitor_labels_unavailable_delay_for_unroutable_packets(self):
        graph = build_emergency_topology(failed_nodes=["router_a", "router_b"])
        event = process_message(graph, _message(1, "Critical"))
        app = AppTest.from_file(PACKET_MONITOR_PAGE)
        app.session_state["packet_events"] = [event]
        app.run()

        self.assertFalse(app.exception)
        self.assertIn("Not available", app.code[0].value)
        self.assertNotIn("—", app.code[0].value)

    def test_analytics_renders_packet_and_leaky_bucket_series(self):
        event = process_message(build_emergency_topology(), _message(1, "High"))
        app = AppTest.from_file(ANALYTICS_PAGE)
        app.session_state["packet_events"] = [event]
        app.session_state["leaky_bucket_result"] = simulate_leaky_bucket(
            [2, 5, 0],
            capacity=4,
            output_rate=1,
        )
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Delivery ratio"], "100.0%")
        self.assertEqual(metrics["Arrivals"], "7")
        self.assertEqual(len(app.get("plotly_chart")), 3)

    def test_analytics_compares_normal_and_reduced_service_profiles(self):
        app = AppTest.from_file(ANALYTICS_PAGE).run()
        app.text_input(key="analytics_comparison_arrivals").set_value("10, 0, 10")
        app.number_input(key="analytics_comparison_capacity").set_value(4)
        app.number_input(key="analytics_comparison_normal_rate").set_value(4)
        app.number_input(key="analytics_comparison_stress_rate").set_value(1)
        next(
            button
            for button in app.form_submit_button
            if button.label == "Compare traffic profiles"
        ).click().run()

        self.assertFalse(app.exception)
        comparison = app.session_state["analytics_profile_comparison"]
        self.assertEqual(comparison["normal"].total_arrivals, 20)
        self.assertGreater(
            comparison["normal"].total_transmitted,
            comparison["stress"].total_transmitted,
        )
        self.assertGreater(
            comparison["stress"].total_dropped,
            comparison["normal"].total_dropped,
        )
        self.assertEqual(len(app.get("plotly_chart")), 2)


if __name__ == "__main__":
    unittest.main()
