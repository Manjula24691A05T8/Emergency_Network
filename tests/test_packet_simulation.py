import json
import unittest
from pathlib import Path

import networkx as nx
from streamlit.testing.v1 import AppTest

from modules.network_topology import build_emergency_topology
from modules.packet_simulation import create_transmission_plan
from modules.topology_3d import add_packet_animation, build_3d_topology_figure


PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "topology_3d.py")


class PacketSimulationTests(unittest.TestCase):
    def test_dijkstra_uses_active_links_for_the_packet_route(self):
        graph = build_emergency_topology([("switch_north", "router_a")])

        plan = create_transmission_plan(
            graph,
            "police_station",
            "ambulance_service",
            "Need medical support.",
        )

        self.assertEqual(plan.route[0], "police_station")
        self.assertEqual(plan.route[-1], "ambulance_service")
        self.assertNotIn(("switch_north", "router_a"), list(zip(plan.route, plan.route[1:])))
        self.assertEqual(plan.packet_size_bytes, len("Need medical support.".encode("utf-8")) + 64)
        self.assertGreater(plan.one_way_delay_ms, 0)
        self.assertGreater(plan.acknowledgement_delay_ms, 0)

    def test_unreachable_destination_has_no_transmission_plan(self):
        graph = build_emergency_topology(
            [
                ("switch_north", "router_a"),
                ("switch_north", "router_b"),
            ]
        )

        with self.assertRaises(nx.NetworkXNoPath):
            create_transmission_plan(
                graph,
                "control_center",
                "ambulance_service",
                "Need medical support.",
            )

    def test_router_failure_recomputes_packet_route_over_available_links(self):
        graph = build_emergency_topology(failed_nodes=["router_a"])

        plan = create_transmission_plan(
            graph,
            "police_station",
            "ambulance_service",
            "Need medical support.",
        )

        self.assertNotIn("router_a", plan.route)
        self.assertIn("router_b", plan.route)
        self.assertTrue(
            all(
                graph.edges[first, second]["status"] == "active"
                for first, second in zip(plan.route, plan.route[1:])
            )
        )

    def test_packet_loss_plan_accounts_for_one_retry(self):
        graph = build_emergency_topology()
        normal = create_transmission_plan(
            graph,
            "police_station",
            "ambulance_service",
            "Need medical support.",
        )
        retried = create_transmission_plan(
            graph,
            "police_station",
            "ambulance_service",
            "Need medical support.",
            inject_packet_loss=True,
        )

        self.assertEqual(retried.retransmissions, 1)
        first_edge = graph.edges[retried.route[0], retried.route[1]]
        first_hop_delay = first_edge["delay_ms"] + (
            retried.packet_size_bytes * 8 / (first_edge["bandwidth_mbps"] * 1_000_000) * 1_000
        )
        self.assertAlmostEqual(
            retried.estimated_delivery_delay_ms - normal.estimated_delivery_delay_ms,
            first_hop_delay / 2,
            places=6,
        )

    def test_animation_includes_route_data_ack_and_drop_frames(self):
        graph = build_emergency_topology()
        plan = create_transmission_plan(
            graph,
            "police_station",
            "ambulance_service",
            "Need medical support.",
            inject_packet_loss=True,
        )
        figure = add_packet_animation(
            build_3d_topology_figure(graph),
            graph,
            plan.route,
            inject_packet_loss=True,
        )

        route_trace = next(trace for trace in figure.data if trace.meta and trace.meta.get("kind") == "packet_route")
        animated_traces = {
            trace.meta["protocol"]: index
            for index, trace in enumerate(figure.data)
            if trace.meta and trace.meta.get("kind") == "animated_packet"
        }
        self.assertEqual(route_trace.meta["route"], list(plan.route))
        self.assertIn("data", animated_traces)
        self.assertIn("ack", animated_traces)
        self.assertIn("drop", animated_traces)
        self.assertTrue(
            any(
                frame.data[list(frame.traces).index(animated_traces["drop"])].x[0] is not None
                for frame in figure.frames
            )
        )
        final_frame = figure.frames[-1]
        acknowledgement = final_frame.data[
            list(final_frame.traces).index(animated_traces["ack"])
        ]
        data_packet = figure.data[animated_traces["data"]]
        self.assertEqual(acknowledgement.x[0], data_packet.x[0])
        self.assertEqual(acknowledgement.y[0], data_packet.y[0])
        self.assertEqual(acknowledgement.z[0], data_packet.z[0])

    def test_page_prepares_the_loss_and_retry_animation(self):
        app = AppTest.from_file(PAGE_PATH).run()
        app.checkbox[0].check()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["packet_transmission_request"]["inject_packet_loss"])
        self.assertEqual(len(app.get("plotly_chart")), 1)
        self.assertEqual(len(app.session_state["recent_activity"]), 1)

    def test_page_failure_control_reroutes_and_restores_prepared_packet(self):
        app = AppTest.from_file(PAGE_PATH)
        app.session_state["packet_transmission_request"] = {
            "source": "police_station",
            "destination": "ambulance_service",
            "message": "Need medical support.",
            "inject_packet_loss": False,
        }
        app.run()
        app.radio[0].set_value("Router").run()
        fail_button = next(
            button for button in app.button if button.key == "3d_fail_selected_router"
        )
        fail_button.click().run()

        self.assertFalse(app.exception)
        self.assertEqual(app.session_state["failed_nodes"], ["router_a"])
        event = app.session_state["last_failure_event"]
        self.assertNotEqual(event["before_route"], event["after_route"])
        self.assertNotIn("router_a", event["after_route"])
        self.assertGreaterEqual(event["route_calculation_ms"], 0)
        figure = json.loads(app.get("plotly_chart")[0].proto.spec)
        route_trace = next(
            trace for trace in figure["data"]
            if trace.get("meta", {}).get("kind") == "packet_route"
        )
        self.assertNotIn("router_a", route_trace["meta"]["route"])
        self.assertIn("router_b", route_trace["meta"]["route"])

        restore_button = next(
            button
            for button in app.button
            if button.key == "3d_restore_selected_router"
        )
        restore_button.click().run()
        self.assertEqual(app.session_state["failed_nodes"], [])
        self.assertEqual(
            app.session_state["last_failure_event"]["action"],
            "restored",
        )
        self.assertIn(
            "router_a",
            app.session_state["last_failure_event"]["after_route"],
        )

    def test_page_withholds_packet_animation_when_routers_disconnect_endpoints(self):
        app = AppTest.from_file(PAGE_PATH)
        app.session_state["failed_nodes"] = ["router_a", "router_b"]
        app.session_state["packet_transmission_request"] = {
            "source": "police_station",
            "destination": "ambulance_service",
            "message": "Need medical support.",
            "inject_packet_loss": False,
        }
        app.run()

        self.assertFalse(app.exception)
        self.assertTrue(any("No active route" in item.value for item in app.error))
        figure = json.loads(app.get("plotly_chart")[0].proto.spec)
        self.assertFalse(
            any(
                trace.get("meta", {}).get("kind") == "packet_route"
                for trace in figure["data"]
            )
        )


if __name__ == "__main__":
    unittest.main()
