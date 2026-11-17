import unittest
from pathlib import Path

import networkx as nx
from streamlit.testing.v1 import AppTest

from algorithms.distance_vector import (
    get_distance_vector_path,
    simulate_distance_vector,
)
from modules.network_topology import active_network, build_emergency_topology


PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "routing.py")


class DistanceVectorTests(unittest.TestCase):
    def test_distance_vector_converges_to_dijkstra_costs(self):
        graph = build_emergency_topology()
        result = simulate_distance_vector(graph)
        network = active_network(graph)

        self.assertTrue(result.converged)
        for source in graph:
            for destination in graph:
                path = get_distance_vector_path(result, source, destination)
                if not path:
                    self.fail(f"No Distance Vector path from {source} to {destination}")
                dijkstra_cost = nx.shortest_path_length(
                    network,
                    source,
                    destination,
                    weight="delay_ms",
                )
                self.assertAlmostEqual(result.tables[source][destination].cost, dijkstra_cost)

    def test_router_failure_removes_failed_node_and_reconverges_over_alternate_path(self):
        graph = build_emergency_topology(failed_nodes=["router_a"])
        result = simulate_distance_vector(graph)

        self.assertTrue(result.converged)
        self.assertNotIn("router_a", result.tables)
        path = get_distance_vector_path(result, "police_station", "ambulance_service")
        self.assertIn("router_b", path)
        self.assertNotIn("router_a", path)

    def test_disconnected_services_have_no_route_and_active_costs_are_validated(self):
        disconnected = build_emergency_topology(
            [
                ("switch_north", "router_a"),
                ("switch_north", "router_b"),
            ]
        )
        result = simulate_distance_vector(disconnected)
        self.assertEqual(
            get_distance_vector_path(result, "control_center", "ambulance_service"),
            [],
        )

        graph = build_emergency_topology()
        graph.edges["police_station", "switch_north"]["delay_ms"] = -1
        with self.assertRaises(ValueError):
            simulate_distance_vector(graph)

    def test_routing_page_compares_algorithms_and_previews_link_failure(self):
        app = AppTest.from_file(PAGE_PATH)
        app.session_state["routing_preview_failure_input"] = True
        app.session_state["routing_failure_link_input"] = (
            "switch_north",
            "router_a",
        )
        app.run()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        state = app.session_state["routing_comparison"]
        self.assertIsNotNone(state["after"])
        self.assertIn("router_b", state["after"]["distance_vector_path"])
        self.assertNotIn("router_a", state["after"]["distance_vector_path"])
        self.assertEqual(len(app.get("plotly_chart")), 1)


if __name__ == "__main__":
    unittest.main()
