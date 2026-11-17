import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from algorithms.go_back_n import GoBackNResult, simulate_go_back_n
from algorithms.sliding_window import SlidingWindowResult, simulate_sliding_window


PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "reliable_transmission.py")


class ReliableTransmissionTests(unittest.TestCase):
    def test_sliding_window_acknowledges_each_packet_within_window(self):
        result = simulate_sliding_window(packet_count=7, window_size=3)

        self.assertEqual(
            [batch.transmitted for batch in result.batches],
            [(1, 2, 3), (4, 5, 6), (7,)],
        )
        self.assertTrue(
            all(
                len(batch.transmitted) <= result.window_size
                and batch.acknowledged == batch.transmitted
                for batch in result.batches
            )
        )
        self.assertEqual(result.total_acknowledged, 7)

    def test_go_back_n_retransmits_missing_and_following_unacknowledged_frames(self):
        result = simulate_go_back_n(
            packet_count=6,
            window_size=3,
            lost_packet=2,
        )

        self.assertEqual(result.rounds[0].transmitted, (1, 2, 3))
        self.assertEqual(result.rounds[0].received, (1,))
        self.assertEqual(result.rounds[0].dropped, (2,))
        self.assertEqual(result.rounds[0].discarded, (3,))
        self.assertEqual(result.rounds[0].cumulative_ack, 1)
        self.assertTrue(result.rounds[0].timeout)
        self.assertEqual(result.rounds[1].transmitted, (2, 3))
        self.assertTrue(result.rounds[1].retransmission)
        self.assertEqual(result.rounds[1].cumulative_ack, 3)
        self.assertEqual(result.retransmission_count, 2)
        self.assertEqual(result.timeout_count, 1)
        self.assertEqual(result.total_acknowledged, 6)

    def test_invalid_packet_counts_window_sizes_and_loss_sequences_are_rejected(self):
        for args in (
            (0, 2, None),
            (4, 0, None),
            (4, 2, 5),
            (4, 2, 0),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                simulate_go_back_n(*args)

    def test_reliable_transmission_page_runs_sliding_window(self):
        app = AppTest.from_file(PAGE_PATH).run()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        self.assertIsInstance(
            app.session_state["reliable_transmission_result"],
            SlidingWindowResult,
        )
        self.assertEqual(len(app.get("plotly_chart")), 1)

    def test_reliable_transmission_page_runs_go_back_n_loss_and_retransmission(self):
        app = AppTest.from_file(PAGE_PATH)
        app.session_state["reliable_protocol_input"] = "Go-Back-N ARQ"
        app.session_state["reliable_inject_loss_input"] = True
        app.session_state["reliable_loss_sequence_input"] = 2
        app.run()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        result = app.session_state["reliable_transmission_result"]
        self.assertIsInstance(result, GoBackNResult)
        self.assertEqual(result.lost_packet, 2)
        self.assertEqual(result.retransmission_count, 3)
        self.assertEqual(len(app.get("plotly_chart")), 1)


if __name__ == "__main__":
    unittest.main()
