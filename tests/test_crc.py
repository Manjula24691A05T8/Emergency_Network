import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from algorithms.crc import calculate_crc, flip_bit, verify_crc


PAGE_PATH = str(Path(__file__).resolve().parents[1] / "pages" / "error_detection.py")


class CRCTests(unittest.TestCase):
    def test_crc_encoding_matches_known_polynomial_division_example(self):
        result = calculate_crc("1101011011", "10011")

        self.assertEqual(result.padded_data, "11010110110000")
        self.assertEqual(result.remainder, "1110")
        self.assertEqual(result.transmitted_frame, "11010110111110")

    def test_crc_verification_accepts_valid_frame_and_detects_single_bit_error(self):
        encoded = calculate_crc("1101011011", "10011")

        valid = verify_crc(encoded.transmitted_frame, encoded.generator)
        corrupted_frame = flip_bit(encoded.transmitted_frame, 4)
        corrupted = verify_crc(corrupted_frame, encoded.generator)

        self.assertTrue(valid.is_valid)
        self.assertEqual(valid.remainder, "0000")
        self.assertFalse(corrupted.is_valid)
        self.assertNotEqual(corrupted.remainder, "0000")

    def test_invalid_binary_inputs_generators_and_bit_positions_are_rejected(self):
        with self.assertRaises(ValueError):
            calculate_crc("10201", "10011")
        with self.assertRaises(ValueError):
            calculate_crc("1011", "1010")
        with self.assertRaises(ValueError):
            verify_crc("101", "10011")
        with self.assertRaises(ValueError):
            flip_bit("1010", 5)

    def test_crc_page_runs_and_reports_injected_corruption(self):
        app = AppTest.from_file(PAGE_PATH)
        app.session_state["crc_inject_error_input"] = True
        app.session_state["crc_error_position_input"] = 4
        app.run()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        self.assertFalse(app.session_state["crc_verification"].is_valid)
        self.assertTrue(any("Corruption detected at injected bit position 4" in item.value for item in app.error))
        self.assertEqual(len(app.expander), 2)

    def test_crc_page_accepts_the_unmodified_generated_frame(self):
        app = AppTest.from_file(PAGE_PATH).run()
        app.form_submit_button[0].click().run()

        self.assertFalse(app.exception)
        self.assertTrue(app.session_state["crc_verification"].is_valid)
        self.assertTrue(any("Frame accepted" in item.value for item in app.success))


if __name__ == "__main__":
    unittest.main()
