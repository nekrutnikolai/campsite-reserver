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


if __name__ == "__main__":
    unittest.main()
