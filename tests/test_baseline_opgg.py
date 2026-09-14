import unittest

from leagueapi import BaselineOPGGTracker


class BaselineOPGGTrackerTests(unittest.TestCase):
    def test_champion_selection_and_counterpicks(self):
        tracker = BaselineOPGGTracker()

        tracker.select_champion("Yasuo")

        self.assertEqual(
            tracker.get_counterpicks(),
            ["renekton", "pantheon", "malphite"],
        )

    def test_unknown_champion_returns_no_counterpicks(self):
        tracker = BaselineOPGGTracker()

        tracker.select_champion("unknown")

        self.assertEqual(tracker.get_counterpicks(), [])

    def test_jungle_respawn_tracking(self):
        tracker = BaselineOPGGTracker()

        respawn = tracker.record_jungle_clear("Blue_Buff", 120)

        self.assertEqual(respawn, 420)
        self.assertEqual(tracker.get_jungle_respawn("blue_buff"), 420)

    def test_unsupported_jungle_camp_raises(self):
        tracker = BaselineOPGGTracker()

        with self.assertRaises(ValueError):
            tracker.record_jungle_clear("invalid_camp", 10)

    def test_spell_tracking_and_ready_check(self):
        tracker = BaselineOPGGTracker()

        ready = tracker.record_spell_use("EnemyMid", "Flash", 100)

        self.assertEqual(ready, 400)
        self.assertFalse(tracker.is_spell_ready("enemymid", "flash", 399))
        self.assertTrue(tracker.is_spell_ready("enemymid", "flash", 400))

    def test_unsupported_spell_raises(self):
        tracker = BaselineOPGGTracker()

        with self.assertRaises(ValueError):
            tracker.record_spell_use("enemytop", "dash", 1)


if __name__ == "__main__":
    unittest.main()
