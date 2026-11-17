from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

from algorithms.go_back_n import simulate_go_back_n
from modules.message_transfer import EmergencyMessage, process_message
from modules.network_topology import build_emergency_topology


APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


class DashboardTests(unittest.TestCase):
    def test_dashboard_shows_topology_derived_counts_and_map(self):
        app = AppTest.from_file(APP_PATH).run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Network nodes"], "10")
        self.assertEqual(metrics["Active links"], "11")
        self.assertEqual(len(app.get("plotly_chart")), 1)
        self.assertNotIn("—", [metric.value for metric in app.metric])
        self.assertEqual(metrics["Frames sent"], "Not run")
        self.assertEqual(metrics["Throughput"], "No packet data")

    def test_dashboard_surfaces_failed_link_state(self):
        app = AppTest.from_file(APP_PATH).run()
        app.session_state["failed_links"] = [("switch_north", "router_a")]
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Active links"], "10")
        self.assertEqual(metrics["Failed links"], "1")
        self.assertEqual(len(app.warning), 1)

    def test_dashboard_counts_router_failure_and_unavailable_links(self):
        app = AppTest.from_file(APP_PATH).run()
        app.session_state["failed_nodes"] = ["router_a"]
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Active routers"], "1")
        self.assertEqual(metrics["Active links"], "8")
        self.assertEqual(metrics["Failed links"], "3")
        self.assertTrue(any("Core Router A is unavailable" in item.value for item in app.error))

    def test_dashboard_surfaces_congestion_from_latest_leaky_bucket_run(self):
        app = AppTest.from_file(APP_PATH)
        app.session_state["dashboard_metrics"] = {
            "congestion_status": "Congested",
            "congestion_dropped_packets": 8,
        }
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Congestion"], "Congested")
        self.assertTrue(any("8 dropped packet(s)" in item.value for item in app.warning))

    def test_dashboard_uses_reliable_transmission_results_for_performance_metrics(self):
        app = AppTest.from_file(APP_PATH)
        app.session_state["reliable_transmission_result"] = simulate_go_back_n(
            packet_count=8,
            window_size=4,
            lost_packet=2,
        )
        app.session_state["reliable_transmission_protocol"] = "Go-Back-N ARQ"
        app.session_state["reliable_transmission_route"] = (
            "police_station",
            "switch_north",
            "router_a",
            "switch_south",
            "ambulance_service",
        )
        app.session_state["reliable_transmission_route_delay_ms"] = 12.5
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Frames sent"], "8")
        self.assertEqual(metrics["Frames acknowledged"], "8")
        self.assertEqual(metrics["Frame loss (attempts)"], "9.1%")
        self.assertEqual(metrics["Route RTT estimate"], "12.5 ms")
        self.assertEqual(metrics["Throughput"], "No packet data")
        self.assertTrue(
            any("LATEST RUN · GO-BACK-N ARQ" in item.value for item in app.markdown)
        )

    def test_dashboard_hides_stale_route_delay_after_link_failure(self):
        app = AppTest.from_file(APP_PATH)
        app.session_state["reliable_transmission_result"] = simulate_go_back_n(4, 2)
        app.session_state["reliable_transmission_route"] = (
            "police_station",
            "switch_north",
            "router_a",
        )
        app.session_state["reliable_transmission_route_delay_ms"] = 12.5
        app.session_state["failed_links"] = [("switch_north", "router_a")]
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Route RTT estimate"], "Route unavailable")

    def test_dashboard_reflects_processed_emergency_message_events(self):
        graph = build_emergency_topology()
        message = EmergencyMessage(
            message_id="MSG-0001",
            sequence=1,
            source="police_station",
            destination="ambulance_service",
            content="Need medical support.",
            priority="Critical",
            queued_at="2026-01-01T00:00:00+00:00",
        )
        event = process_message(graph, message)
        app = AppTest.from_file(APP_PATH)
        app.session_state["packet_events"] = [event]
        app.run()

        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Messages processed"], "1")
        self.assertEqual(metrics["Messages delivered"], "1")
        self.assertEqual(metrics["Message loss"], "0.0%")
        self.assertTrue(metrics["Throughput"].endswith(" Mbps"))
        self.assertGreater(float(metrics["Average message delay"].replace(" ms", "")), 0)
        self.assertEqual(len(app.get("plotly_chart")), 2)


if __name__ == "__main__":
    unittest.main()
