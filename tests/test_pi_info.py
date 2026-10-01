import unittest

from challenge import pi_info

from .support import FakePi


class ModelMatchTests(unittest.TestCase):
    TABLE = [
        ("Pi 4 Model B", "Raspberry Pi 4 Model B Rev 1.4", "4b", "4b", True),
        ("Raspberry Pi 5", "Raspberry Pi 5 Model B Rev 1.0", "5", "5b", True),
        ("Zero 2 W", "Raspberry Pi Zero 2 W Rev 1.0", "zero2w", "zero2w", True),
        ("Pi 3B+", "Raspberry Pi 4 Model B Rev 1.2", "3b", "4b", False),
    ]

    def test_table(self):
        for typed, detected, typed_n, detected_n, match in self.TABLE:
            with self.subTest(typed=typed):
                self.assertEqual(pi_info.normalize_model(typed), typed_n)
                self.assertEqual(pi_info.normalize_model(detected), detected_n)
                self.assertEqual(pi_info.model_matches(typed, detected), match)

    def test_empty_normalized_value_does_not_match(self):
        self.assertFalse(pi_info.model_matches("Raspberry Pi", "Raspberry Pi 4 Model B Rev 1.4"))


class DetectionTests(unittest.TestCase):
    def test_reads_fake_files(self):
        with FakePi():
            env = pi_info.Environment({"SUPERVISOR_ENABLED": "1",
                                       "SUPERVISOR_PROCESS_NAME": "app"})
        self.assertEqual(env.model, "Raspberry Pi 4 Model B Rev 1.4")  # null byte stripped
        self.assertEqual(env.boot_id, "a1b2c3d4")
        self.assertEqual(env.uptime, 41.2)
        self.assertEqual(env.os_name, "Debian GNU/Linux 12 (bookworm)")
        self.assertTrue(env.supervised)
        self.assertEqual(env.process_name, "app")

    def test_not_a_pi(self):
        with FakePi(model=None):
            env = pi_info.Environment({})
        self.assertIsNone(env.model)
        self.assertFalse(env.supervised)

    def test_format_uptime(self):
        self.assertEqual(pi_info.format_uptime(41.2), "41 s")
        self.assertEqual(pi_info.format_uptime(600), "10 min")
        self.assertEqual(pi_info.format_uptime(3 * 3600 + 120), "3 h 2 min")
        self.assertEqual(pi_info.format_uptime(None), "unknown")


if __name__ == "__main__":
    unittest.main()
