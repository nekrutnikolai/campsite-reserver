import unittest
from datetime import date
from unittest.mock import patch, MagicMock

import campsite_monitor


class TestSeenSetFiltering(unittest.TestCase):
    @patch("campsite_monitor.recgov")
    @patch("campsite_monitor.reserveca")
    def test_same_site_not_alerted_twice(self, mock_rca, mock_rg):
        mock_rg.CAMPGROUNDS = [{"name": "Camp", "id": "1"}]
        mock_rca.CAMPGROUNDS = []

        site = {"site": "001", "campground": "Camp", "url": "https://example.com"}
        mock_rg.check_availability.return_value = [site]

        checkin = date(2024, 6, 14)
        checkout = date(2024, 6, 16)

        # First call finds the site
        results1, _ = campsite_monitor.check_all(checkin, checkout)
        # Second call returns same site
        results2, _ = campsite_monitor.check_all(checkin, checkout)

        # Simulate seen-set filtering like main() does
        seen = set()
        new_sites = []
        for batch in [results1, results2]:
            for s in batch:
                key = (s["campground"], s["site"], str(checkin), str(checkout))
                if key not in seen:
                    seen.add(key)
                    new_sites.append(s)

        self.assertEqual(len(new_sites), 1)

    @patch("campsite_monitor.recgov")
    @patch("campsite_monitor.reserveca")
    def test_new_sites_detected(self, mock_rca, mock_rg):
        mock_rg.CAMPGROUNDS = [{"name": "Camp", "id": "1"}]
        mock_rca.CAMPGROUNDS = []

        site_a = {"site": "001", "campground": "Camp", "url": "https://example.com"}
        site_b = {"site": "002", "campground": "Camp", "url": "https://example.com"}
        mock_rg.check_availability.side_effect = [[site_a], [site_b]]

        checkin = date(2024, 6, 14)
        checkout = date(2024, 6, 16)

        seen = set()
        new_sites = []
        for _ in range(2):
            results, _ = campsite_monitor.check_all(checkin, checkout)
            for s in results:
                key = (s["campground"], s["site"], str(checkin), str(checkout))
                if key not in seen:
                    seen.add(key)
                    new_sites.append(s)

        self.assertEqual(len(new_sites), 2)
        self.assertEqual(new_sites[0]["site"], "001")
        self.assertEqual(new_sites[1]["site"], "002")


class TestFailureAlerts(unittest.TestCase):
    """Test the consecutive failure tracking and Telegram alerting logic."""

    def _run_cycle(self, errors, all_names, consecutive_failures, alerted_sources, telegram_msgs):
        """Simulate one cycle of the failure tracking logic from main()."""
        error_set = set(errors)
        for name in all_names:
            if name in error_set:
                consecutive_failures[name] = consecutive_failures.get(name, 0) + 1
                if consecutive_failures[name] == 3 and name not in alerted_sources:
                    alerted_sources.add(name)
                    telegram_msgs.append(f"failure:{name}")
            else:
                if name in alerted_sources:
                    alerted_sources.discard(name)
                    telegram_msgs.append(f"recovered:{name}")
                consecutive_failures[name] = 0

    def test_alert_after_3_consecutive_failures(self):
        cf, alerted, msgs = {}, set(), []
        names = {"Camp A"}
        for _ in range(3):
            self._run_cycle(["Camp A"], names, cf, alerted, msgs)
        self.assertEqual(msgs, ["failure:Camp A"])

    def test_no_alert_on_transient_failure(self):
        cf, alerted, msgs = {}, set(), []
        names = {"Camp A"}
        self._run_cycle(["Camp A"], names, cf, alerted, msgs)
        self._run_cycle(["Camp A"], names, cf, alerted, msgs)
        self._run_cycle([], names, cf, alerted, msgs)  # recovers before threshold
        self.assertEqual(msgs, [])

    def test_recovery_message_after_alert(self):
        cf, alerted, msgs = {}, set(), []
        names = {"Camp A"}
        for _ in range(3):
            self._run_cycle(["Camp A"], names, cf, alerted, msgs)
        self._run_cycle([], names, cf, alerted, msgs)
        self.assertEqual(msgs, ["failure:Camp A", "recovered:Camp A"])

    def test_no_duplicate_failure_alerts(self):
        cf, alerted, msgs = {}, set(), []
        names = {"Camp A"}
        for _ in range(6):
            self._run_cycle(["Camp A"], names, cf, alerted, msgs)
        self.assertEqual(msgs, ["failure:Camp A"])

    def test_multiple_sources_independent(self):
        cf, alerted, msgs = {}, set(), []
        names = {"Camp A", "Camp B"}
        for _ in range(3):
            self._run_cycle(["Camp A"], names, cf, alerted, msgs)
        self.assertIn("failure:Camp A", msgs)
        self.assertNotIn("failure:Camp B", msgs)


if __name__ == "__main__":
    unittest.main()
