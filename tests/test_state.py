import os
import tempfile
import unittest

from challenge import state


class StateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_start_counter_increments(self):
        self.assertEqual([state.next_start_count(self.dir) for _ in range(3)], [1, 2, 3])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "start_count.tmp")))

    def test_corrupt_counter_restarts(self):
        with open(os.path.join(self.dir, "start_count"), "w") as f:
            f.write("garbage")
        self.assertEqual(state.next_start_count(self.dir), 1)

    def test_boot_id_change_detected(self):
        self.assertTrue(state.check_boot(self.dir, "a1b2c3d4"))
        self.assertFalse(state.check_boot(self.dir, "a1b2c3d4"))
        self.assertTrue(state.check_boot(self.dir, "e5f6a7b8"))
        self.assertFalse(state.check_boot(self.dir, "e5f6a7b8"))


if __name__ == "__main__":
    unittest.main()
