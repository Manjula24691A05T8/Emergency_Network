import json
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from algorithms.leaky_bucket import (
    LeakyBucketResult,
    compare_leaky_bucket_profiles,
    simulate_leaky_bucket,
)
from modules.traffic_input import parse_arrivals


ROOT = Path(__file__).resolve().parents[1]
CONGESTION_PAGE_PATH = str(ROOT / "pages" / "congestion.py")
TOPOLOGY_3D_PAGE_PATH = str(ROOT / "pages" / "topology_3d.py")


class LeakyBucketTests(unittest.TestCase):
    def test_finite_buffer_drops_overflow_and_leaks_at_configured_rate(self):
        result = simulate_leaky_bucket([2, 5, 0], capacity=3, output_rate=1)

        self.assertEqual(result.total_arrivals, 7)
        self.assertEqual(result.total_admitted, 4)
        self.assertEqual(result.total_transmitted, 3)
        self.assertEqual(result.total_dropped, 3)
        self.assertEqual(
            [
                (
                    step.queued_before_leak,
                    step.transmitted,
                    step.dropped,
                    step.queued_after_leak,
                )
                for step in result.steps
            ],
            [(2, 1, 0, 1), (3, 1, 3, 2), (2, 1, 0, 1)],
        )
        self.assertEqual(result.congestion_status, "Congested")

    def test_full_buffer_without_drops_is_reported_at_capacity(self):
        result = simulate_leaky_bucket([3], capacity=3, output_rate=3)

        self.assertEqual(result.total_dropped, 0)
        self.assertEqual(result.congestion_status, "At capacity")
        self.assertEqual(result.congestion_rate_percent, 100)

    def test_invalid_capacity_rate_and_arrival_values_are_rejected(self):
        for args in (
            ([1], 0, 1),
            ([1], 2, 0),
            ([1, -1], 2, 1),
            ([], 2, 1),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                simulate_leaky_bucket(*args)

    def test_comparison_uses_same_arrivals_and_stress_rate_increases_drops(self):
        normal, stress = compare_leaky_bucket_profiles(
            [10, 0, 10],
            capacity=4,
            normal_output_rate=4,
            stress_output_rate=1,
        )

        self.assertEqual(normal.total_arrivals, stress.total_arrivals)
        self.assertGreater(normal.total_transmitted, stress.total_transmitted)
        self.assertGreater(stress.total_dropped, normal.total_dropped)

    def test_comparison_rejects_non_stress_service_rate(self):
        with self.assertRaisesRegex(ValueError, "must be lower"):
            compare_leaky_bucket_profiles([1], 4, 2, 2)

    def test_parse_arrivals_validates_slot_count_and_integer_values(self):
        self.assertEqual(parse_arrivals(" 2, 0, 7 "), [2, 0, 7])
        for value in ("", "1,,2", "1, -2", "1, 2.5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_arrivals(value)
        with self.assertRaisesRegex(ValueError, "no more than 2"):
            parse_arrivals("1,2,3", max_time_slots=2)

    def test_congestion_page_runs_and_persists_simulation(self):
        app = AppTest.from_file(CONGESTION_PAGE_PATH).run()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        result = app.session_state["leaky_bucket_result"]
        self.assertIsInstance(result, LeakyBucketResult)
        self.assertEqual(result.total_dropped, 8)
        self.assertEqual(app.session_state["dashboard_metrics"]["congestion_status"], "Congested")
        self.assertEqual(len(app.get("plotly_chart")), 1)

    def test_3d_page_displays_queue_matching_selected_simulation_slot(self):
        result = simulate_leaky_bucket([2, 1, 8, 2], capacity=8, output_rate=2)
        app = AppTest.from_file(TOPOLOGY_3D_PAGE_PATH)
        app.session_state["leaky_bucket_result"] = result
        app.session_state["leaky_bucket_router"] = "router_a"
        app.session_state["leaky_bucket_selected_tick"] = 3
        app.run()

        self.assertFalse(app.exception)
        figure = json.loads(app.get("plotly_chart")[0].proto.spec)
        queue_trace = next(
            trace for trace in figure["data"]
            if trace.get("meta", {}).get("kind") == "router_queue"
        )
        self.assertEqual(queue_trace["meta"]["router"], "router_a")
        self.assertEqual(queue_trace["meta"]["occupancy"], 8)
        self.assertEqual(queue_trace["meta"]["capacity"], 8)
        self.assertEqual(queue_trace["meta"]["tick"], 3)


if __name__ == "__main__":
    unittest.main()
