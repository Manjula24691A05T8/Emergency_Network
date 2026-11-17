import unittest
from pathlib import Path

from modules.network_topology import build_emergency_topology
from modules.topology_3d import (
    add_packet_animation,
    add_router_queue_visualization,
    build_3d_topology_figure,
)
from streamlit.testing.v1 import AppTest


PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "topology_3d.py")
TOPOLOGY_PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "topology.py")


class ThreeDimensionalTopologyTests(unittest.TestCase):
    def test_scene_has_hardware_meshes_and_one_cable_per_network_link(self):
        graph = build_emergency_topology()
        figure = build_3d_topology_figure(graph)

        hardware_meshes = [trace for trace in figure.data if trace.type == "mesh3d"]
        cables = [
            trace
            for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "cable"
        ]
        self.assertGreater(len(hardware_meshes), 5)
        self.assertEqual(len(cables), graph.number_of_edges())
        self.assertTrue(all(trace.meta["status"] == "active" for trace in cables))

    def test_failed_network_link_uses_failed_cable_render_state(self):
        graph = build_emergency_topology([("switch_north", "router_a")])
        figure = build_3d_topology_figure(graph)

        cables = [
            trace
            for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "cable"
        ]
        failed_cables = [trace for trace in cables if trace.meta["status"] == "failed"]
        self.assertEqual(len(failed_cables), 1)
        self.assertEqual(failed_cables[0].line.dash, "dash")

    def test_failed_router_marks_device_and_attached_cables_unavailable(self):
        graph = build_emergency_topology(failed_nodes=["router_a"])
        figure = build_3d_topology_figure(graph)

        failed_cables = [
            trace
            for trace in figure.data
            if trace.meta
            and trace.meta.get("kind") == "cable"
            and trace.meta["status"] == "failed"
        ]
        device_labels = next(
            trace
            for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "device_labels"
        )
        router_index = list(device_labels.text).index("R-A")

        self.assertEqual(len(failed_cables), 3)
        self.assertEqual(device_labels.marker.symbol[router_index], "x")
        self.assertEqual(device_labels.marker.color[router_index], "#d75a5e")
        self.assertEqual(device_labels.customdata[router_index][4], "Failed")

    def test_queue_visualization_reflects_buffer_capacity_and_full_state(self):
        graph = build_emergency_topology()
        figure = add_router_queue_visualization(
            build_3d_topology_figure(graph),
            graph,
            "router_a",
            occupancy=4,
            capacity=4,
            tick=6,
        )
        queue_trace = next(
            trace for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "router_queue"
        )
        status_trace = next(
            trace for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "router_queue_status"
        )

        self.assertEqual(queue_trace.meta["occupancy"], 4)
        self.assertEqual(queue_trace.meta["capacity"], 4)
        self.assertEqual(queue_trace.marker.color[0], "#d75a5e")
        self.assertEqual(status_trace.meta["full"], True)

    def test_reduced_detail_mode_reduces_mesh_geometry(self):
        graph = build_emergency_topology()
        detailed = build_3d_topology_figure(graph)
        reduced = build_3d_topology_figure(graph, reduced_detail=True)

        def vertex_count(figure):
            return sum(len(trace.x) for trace in figure.data if trace.type == "mesh3d")

        self.assertLess(vertex_count(reduced), vertex_count(detailed))

    def test_reduced_motion_shows_static_route_and_does_not_create_frames(self):
        graph = build_emergency_topology()
        figure = add_packet_animation(
            build_3d_topology_figure(graph),
            graph,
            ["police_station", "switch_north", "router_a", "switch_south", "ambulance_service"],
            inject_packet_loss=True,
            reduced_motion=True,
        )

        self.assertEqual(len(figure.frames), 0)
        route_trace = next(
            trace for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "packet_route"
        )
        self.assertEqual(
            route_trace.meta["route"],
            ["police_station", "switch_north", "router_a", "switch_south", "ambulance_service"],
        )
        packets = [
            trace for trace in figure.data
            if trace.meta and trace.meta.get("kind") == "animated_packet"
        ]
        self.assertTrue(all(trace.x[0] is not None for trace in packets))

    def test_device_inspector_lists_actual_attached_link_neighbor(self):
        app = AppTest.from_file(PAGE_PATH).run()

        self.assertFalse(app.exception)
        link_details = [
            caption.value
            for caption in app.caption
            if " · ACTIVE · " in caption.value
        ]
        self.assertEqual(len(link_details), 1)
        self.assertIn("North Access Switch", link_details[0])
        self.assertNotIn("Emergency Control Center", link_details[0])

    def test_reduced_motion_mode_renders_prepared_route_without_animation(self):
        app = AppTest.from_file(PAGE_PATH)
        app.session_state["reduced_motion"] = True
        app.session_state["packet_transmission_request"] = {
            "source": "police_station",
            "destination": "ambulance_service",
            "message": "Request backup.",
            "inject_packet_loss": True,
        }
        app.run()

        self.assertFalse(app.exception)
        self.assertTrue(
            any("Reduced motion is enabled" in item.value for item in app.info)
        )

    def test_2d_topology_controls_fail_and_restore_router(self):
        app = AppTest.from_file(TOPOLOGY_PAGE_PATH)
        app.session_state["topology_selected_router"] = "router_a"
        app.run()
        fail_button = next(
            button for button in app.button if button.key == "topology_fail_router"
        )
        fail_button.click().run()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["failed_nodes"], ["router_a"])
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Routers / switches"], "1 / 2")
        self.assertEqual(metrics["Active connections"], "8")

        restore_button = next(
            button for button in app.button if button.key == "topology_restore_router"
        )
        restore_button.click().run()
        self.assertEqual(app.session_state["failed_nodes"], [])


if __name__ == "__main__":
    unittest.main()
