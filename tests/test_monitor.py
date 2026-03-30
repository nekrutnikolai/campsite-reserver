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


class TestGoneAlerts(unittest.TestCase):
    """Test the previously_available tracking logic for gone alerts."""

    def _run_cycle(self, available, checkin, checkout, previously_available):
        """Simulate one cycle of the gone-detection logic from main().

        Returns (new_sites, gone_sites, updated_previously_available).
        """
        now_available = {}
        for site in available:
            key = (site["campground"], site["site"], str(checkin), str(checkout))
            now_available[key] = site

        new_sites = []
        for key, site in now_available.items():
            if key not in previously_available:
                new_sites.append(site)

        gone_sites = []
        for key, site in previously_available.items():
            if key[2] == str(checkin) and key[3] == str(checkout) and key not in now_available:
                gone_sites.append(site)

        # Update: remove old keys for this date range, add new
        updated = {
            k: v for k, v in previously_available.items()
            if not (k[2] == str(checkin) and k[3] == str(checkout))
        }
        updated.update(now_available)

        return new_sites, gone_sites, updated

    def test_gone_alert_when_site_disappears(self):
        checkin = date(2024, 6, 14)
        checkout = date(2024, 6, 16)
        site_a = {"site": "001", "campground": "Camp", "url": "https://example.com"}
        previously_available = {}

        # Cycle 1: site_a available
        new, gone, previously_available = self._run_cycle(
            [site_a], checkin, checkout, previously_available
        )
        self.assertEqual(len(new), 1)
        self.assertEqual(len(gone), 0)

        # Cycle 2: no sites available
        new, gone, previously_available = self._run_cycle(
            [], checkin, checkout, previously_available
        )
        self.assertEqual(len(new), 0)
        self.assertEqual(len(gone), 1)
        self.assertEqual(gone[0]["site"], "001")

    def test_reappearing_site_alerts_again(self):
        checkin = date(2024, 6, 14)
        checkout = date(2024, 6, 16)
        site_a = {"site": "001", "campground": "Camp", "url": "https://example.com"}
        previously_available = {}

        # Cycle 1: site_a available
        new, gone, previously_available = self._run_cycle(
            [site_a], checkin, checkout, previously_available
        )
        self.assertEqual(len(new), 1)

        # Cycle 2: site_a gone
        new, gone, previously_available = self._run_cycle(
            [], checkin, checkout, previously_available
        )
        self.assertEqual(len(gone), 1)

        # Cycle 3: site_a available again — should re-alert as new
        new, gone, previously_available = self._run_cycle(
            [site_a], checkin, checkout, previously_available
        )
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["site"], "001")

    def test_no_gone_for_different_date_range(self):
        checkin_a = date(2024, 6, 14)
        checkout_a = date(2024, 6, 16)
        checkin_b = date(2024, 7, 1)
        checkout_b = date(2024, 7, 3)
        site_a = {"site": "001", "campground": "Camp", "url": "https://example.com"}
        previously_available = {}

        # Cycle 1: site_a available for dates A
        new, gone, previously_available = self._run_cycle(
            [site_a], checkin_a, checkout_a, previously_available
        )
        self.assertEqual(len(new), 1)

        # Cycle 2: check dates B with no sites — should NOT trigger gone for dates A site
        new, gone, previously_available = self._run_cycle(
            [], checkin_b, checkout_b, previously_available
        )
        self.assertEqual(len(new), 0)
        self.assertEqual(len(gone), 0)


class TestDateValidation(unittest.TestCase):
    """Test that invalid date ranges are rejected."""

    @patch("dotenv.load_dotenv")
    @patch("sys.argv", ["prog", "--dates", "2024-06-16:2024-06-14", "--once", "--no-telegram"])
    def test_checkout_before_checkin(self, mock_dotenv):
        with self.assertRaises(SystemExit):
            campsite_monitor.main()


if __name__ == "__main__":
    unittest.main()
