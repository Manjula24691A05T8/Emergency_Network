import unittest

from modules.network_topology import (
    CONTROL_CENTER,
    build_emergency_topology,
    get_available_paths,
    get_topology_metrics,
)


class EmergencyTopologyTests(unittest.TestCase):
    def test_default_topology_has_redundant_routes(self):
        graph = build_emergency_topology()
        metrics = get_topology_metrics(graph)

        self.assertEqual(graph.number_of_nodes(), 10)
        self.assertEqual(graph.number_of_edges(), 11)
        self.assertEqual(metrics["network_health"], "Operational")
        self.assertEqual(metrics["reachable_services"], metrics["total_services"])
        self.assertGreaterEqual(
            len(get_available_paths(graph, CONTROL_CENTER, "ambulance_service")),
            2,
        )

    def test_single_core_link_failure_preserves_service_connectivity(self):
        graph = build_emergency_topology([("switch_north", "router_a")])
        metrics = get_topology_metrics(graph)

        self.assertEqual(metrics["network_health"], "Degraded")
        self.assertEqual(metrics["active_connections"], 10)
        self.assertEqual(metrics["reachable_services"], metrics["total_services"])
        self.assertTrue(get_available_paths(graph, CONTROL_CENTER, "ambulance_service"))

    def test_failure_of_both_core_uplinks_disconnects_services(self):
        graph = build_emergency_topology(
            [
                ("switch_north", "router_a"),
                ("switch_north", "router_b"),
            ]
        )
        metrics = get_topology_metrics(graph)

        self.assertEqual(metrics["network_health"], "Critical")
        self.assertEqual(metrics["reachable_services"], 3)
        self.assertEqual(
            get_available_paths(graph, CONTROL_CENTER, "ambulance_service"),
            [],
        )

    def test_router_failure_disables_device_and_incident_links(self):
        graph = build_emergency_topology(failed_nodes=["router_a"])
        metrics = get_topology_metrics(graph)

        self.assertEqual(graph.nodes["router_a"]["status"], "failed")
        self.assertEqual(metrics["active_routers"], 1)
        self.assertEqual(metrics["failed_connections"], 3)
        self.assertEqual(metrics["network_health"], "Degraded")
        path = get_available_paths(graph, "police_station", "ambulance_service")[0]
        self.assertNotIn("router_a", path)
        self.assertIn("router_b", path)

    def test_failure_of_both_routers_disconnects_network_services(self):
        graph = build_emergency_topology(failed_nodes=["router_a", "router_b"])
        metrics = get_topology_metrics(graph)

        self.assertEqual(metrics["active_routers"], 0)
        self.assertEqual(metrics["network_health"], "Critical")
        self.assertEqual(
            get_available_paths(graph, "police_station", "ambulance_service"),
            [],
        )

    def test_unknown_failed_link_is_rejected(self):
        with self.assertRaises(ValueError):
            build_emergency_topology([("router_x", "router_y")])

    def test_non_router_node_failure_is_rejected(self):
        with self.assertRaises(ValueError):
            build_emergency_topology(failed_nodes=["police_station"])


if __name__ == "__main__":
    unittest.main()
