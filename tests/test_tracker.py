import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from campsite_monitor.tracker import AvailabilityTracker, FailureTracker, NetworkMonitor


# ---------------------------------------------------------------------------
# AvailabilityTracker
# ---------------------------------------------------------------------------

class TestAvailabilityTracker(unittest.TestCase):

    def _site(self, campground="Camp", site_id="001", url="https://example.com"):
        return {"campground": campground, "site": site_id, "url": url}

    def test_new_site_detected(self):
        tracker = AvailabilityTracker()
        new, gone = tracker.update(
            [self._site()], date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["site"], "001")
        self.assertEqual(len(gone), 0)

    def test_same_site_not_alerted_twice(self):
        tracker = AvailabilityTracker()
        site = self._site()
        tracker.update([site], date(2024, 6, 14), date(2024, 6, 16))
        new, gone = tracker.update([site], date(2024, 6, 14), date(2024, 6, 16))
        self.assertEqual(new, [])

    def test_different_sites_both_detected(self):
        tracker = AvailabilityTracker()
        site_a = self._site(site_id="001")
        site_b = self._site(site_id="002")
        new, _ = tracker.update(
            [site_a, site_b], date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(len(new), 2)
        ids = {s["site"] for s in new}
        self.assertEqual(ids, {"001", "002"})

    def test_gone_site_detected(self):
        tracker = AvailabilityTracker()
        site = self._site()
        tracker.update([site], date(2024, 6, 14), date(2024, 6, 16))
        new, gone = tracker.update([], date(2024, 6, 14), date(2024, 6, 16))
        self.assertEqual(len(gone), 1)
        self.assertEqual(gone[0]["site"], "001")
        self.assertEqual(new, [])

    def test_reappearing_site_alerts_again(self):
        tracker = AvailabilityTracker()
        site = self._site()
        checkin, checkout = date(2024, 6, 14), date(2024, 6, 16)

        # Cycle 1: appears
        new, _ = tracker.update([site], checkin, checkout)
        self.assertEqual(len(new), 1)

        # Cycle 2: disappears
        _, gone = tracker.update([], checkin, checkout)
        self.assertEqual(len(gone), 1)

        # Cycle 3: reappears — should be reported as new again
        new, _ = tracker.update([site], checkin, checkout)
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["site"], "001")

    def test_no_gone_for_different_date_range(self):
        tracker = AvailabilityTracker()
        site = self._site()

        # Add site for date range A
        tracker.update([site], date(2024, 6, 14), date(2024, 6, 16))

        # Check date range B with no sites — should NOT report gone for A
        new, gone = tracker.update([], date(2024, 7, 1), date(2024, 7, 3))
        self.assertEqual(gone, [])
        self.assertEqual(new, [])

    def test_multiple_date_ranges_independent(self):
        tracker = AvailabilityTracker()
        site_a = self._site(site_id="001")
        site_b = self._site(site_id="002")

        # Add site_a for dates A
        new_a, _ = tracker.update(
            [site_a], date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(len(new_a), 1)

        # Add site_b for dates B
        new_b, _ = tracker.update(
            [site_b], date(2024, 7, 1), date(2024, 7, 3)
        )
        self.assertEqual(len(new_b), 1)

        # Remove site_a from dates A — should only report site_a gone, not site_b
        new, gone = tracker.update([], date(2024, 6, 14), date(2024, 6, 16))
        self.assertEqual(len(gone), 1)
        self.assertEqual(gone[0]["site"], "001")

        # site_b should still be tracked for dates B
        self.assertIn(
            ("Camp", "002", "2024-07-01", "2024-07-03"),
            tracker.previously_available,
        )

    def test_reset_daily(self):
        tracker = AvailabilityTracker()
        tracker.update([self._site()], date(2024, 6, 14), date(2024, 6, 16))
        self.assertEqual(tracker.sites_found_today, 1)
        self.assertEqual(tracker.total_tracked, 1)

        tracker.reset_daily()

        self.assertEqual(tracker.sites_found_today, 0)
        self.assertEqual(tracker.total_tracked, 1)  # total_found persists

    def test_total_tracked_property(self):
        tracker = AvailabilityTracker()
        self.assertEqual(tracker.total_tracked, 0)

        tracker.update([self._site(site_id="001")], date(2024, 6, 14), date(2024, 6, 16))
        self.assertEqual(tracker.total_tracked, 1)

        tracker.update(
            [self._site(site_id="001"), self._site(site_id="002")],
            date(2024, 6, 14),
            date(2024, 6, 16),
        )
        self.assertEqual(tracker.total_tracked, 2)

    def test_with_db_record_find_called(self):
        db = MagicMock()
        db.record_find.return_value = True  # new find
        tracker = AvailabilityTracker(db=db)
        site = self._site()

        new, _ = tracker.update([site], date(2024, 6, 14), date(2024, 6, 16))

        self.assertEqual(len(new), 1)
        db.record_find.assert_called_once_with(
            "Camp", "001", "2024-06-14", "2024-06-16", "https://example.com"
        )

    def test_with_db_dedup_across_restart(self):
        db = MagicMock()
        db.record_find.return_value = False  # already known from previous run
        tracker = AvailabilityTracker(db=db)
        site = self._site()

        new, _ = tracker.update([site], date(2024, 6, 14), date(2024, 6, 16))

        self.assertEqual(new, [])
        self.assertEqual(tracker.sites_found_today, 0)


# ---------------------------------------------------------------------------
# FailureTracker
# ---------------------------------------------------------------------------

class TestFailureTracker(unittest.TestCase):

    def test_alert_after_threshold(self):
        ft = FailureTracker()
        names = ["Camp A"]
        for _ in range(2):
            failed, recovered = ft.update(["Camp A"], names)
            self.assertEqual(failed, [])
        failed, recovered = ft.update(["Camp A"], names)
        self.assertEqual(failed, ["Camp A"])

    def test_no_alert_on_transient_failure(self):
        ft = FailureTracker()
        names = ["Camp A"]
        ft.update(["Camp A"], names)
        ft.update(["Camp A"], names)
        # Recovers before threshold
        failed, recovered = ft.update([], names)
        self.assertEqual(failed, [])
        self.assertEqual(recovered, [])

    def test_recovery_after_alert(self):
        ft = FailureTracker()
        names = ["Camp A"]
        for _ in range(3):
            ft.update(["Camp A"], names)
        failed, recovered = ft.update([], names)
        self.assertEqual(recovered, ["Camp A"])

    def test_no_duplicate_alerts(self):
        ft = FailureTracker()
        names = ["Camp A"]
        alerts = []
        for _ in range(6):
            failed, _ = ft.update(["Camp A"], names)
            alerts.extend(failed)
        self.assertEqual(alerts, ["Camp A"])

    def test_multiple_sources_independent(self):
        ft = FailureTracker()
        names = ["Camp A", "Camp B"]
        for _ in range(3):
            ft.update(["Camp A"], names)
        self.assertIn("Camp A", ft.alerted)
        self.assertNotIn("Camp B", ft.alerted)

    def test_custom_threshold(self):
        ft = FailureTracker(threshold=5)
        names = ["Camp A"]
        alerts = []
        for _ in range(3):
            failed, _ = ft.update(["Camp A"], names)
            alerts.extend(failed)
        self.assertEqual(alerts, [])
        # Two more to reach 5
        for _ in range(2):
            failed, _ = ft.update(["Camp A"], names)
            alerts.extend(failed)
        self.assertEqual(alerts, ["Camp A"])


# ---------------------------------------------------------------------------
# NetworkMonitor
# ---------------------------------------------------------------------------

class TestNetworkMonitor(unittest.TestCase):

    @patch("campsite_monitor.tracker.time")
    def test_up_returns_up(self, mock_time):
        nm = NetworkMonitor()
        result = nm.check(True)
        self.assertEqual(result, "up")

    @patch("campsite_monitor.tracker.time")
    def test_first_down_returns_silent(self, mock_time):
        mock_time.monotonic.return_value = 1000.0
        nm = NetworkMonitor()
        result = nm.check(False)
        self.assertEqual(result, "down_silent")
        self.assertEqual(nm.down_since, 1000.0)

    @patch("campsite_monitor.tracker.time")
    def test_down_before_threshold_returns_silent(self, mock_time):
        nm = NetworkMonitor()
        mock_time.monotonic.return_value = 1000.0
        nm.check(False)  # first down

        mock_time.monotonic.return_value = 1200.0  # 200s later, under 300s threshold
        result = nm.check(False)
        self.assertEqual(result, "down_silent")
        self.assertFalse(nm.alerted)

    @patch("campsite_monitor.tracker.time")
    def test_down_after_threshold_returns_alert(self, mock_time):
        nm = NetworkMonitor()
        mock_time.monotonic.return_value = 1000.0
        nm.check(False)

        mock_time.monotonic.return_value = 1301.0  # >300s later
        result = nm.check(False)
        self.assertEqual(result, "down_alert")
        self.assertTrue(nm.alerted)

    @patch("campsite_monitor.tracker.time")
    def test_alert_only_once(self, mock_time):
        nm = NetworkMonitor()
        mock_time.monotonic.return_value = 1000.0
        nm.check(False)

        mock_time.monotonic.return_value = 1301.0
        result1 = nm.check(False)
        self.assertEqual(result1, "down_alert")

        mock_time.monotonic.return_value = 1500.0
        result2 = nm.check(False)
        self.assertEqual(result2, "down_silent")

    @patch("campsite_monitor.tracker.time")
    def test_recovery_after_alert(self, mock_time):
        nm = NetworkMonitor()
        mock_time.monotonic.return_value = 1000.0
        nm.check(False)

        mock_time.monotonic.return_value = 1301.0
        nm.check(False)  # triggers alert

        result = nm.check(True)
        self.assertEqual(result, "recovered")
        self.assertIsNone(nm.down_since)
        self.assertFalse(nm.alerted)

    @patch("campsite_monitor.tracker.time")
    def test_recovery_without_alert(self, mock_time):
        nm = NetworkMonitor()
        mock_time.monotonic.return_value = 1000.0
        nm.check(False)  # brief down

        result = nm.check(True)  # back up before threshold
        self.assertEqual(result, "up")
        self.assertIsNone(nm.down_since)

    @patch("campsite_monitor.tracker.time")
    def test_custom_threshold(self, mock_time):
        nm = NetworkMonitor(threshold=60)
        mock_time.monotonic.return_value = 1000.0
        nm.check(False)

        # At 59s: still silent
        mock_time.monotonic.return_value = 1059.0
        result = nm.check(False)
        self.assertEqual(result, "down_silent")

        # At 61s: alert
        mock_time.monotonic.return_value = 1061.0
        result = nm.check(False)
        self.assertEqual(result, "down_alert")


if __name__ == "__main__":
    unittest.main()
