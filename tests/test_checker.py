import unittest
from unittest.mock import patch, MagicMock
from datetime import date

from campsite_monitor.checker import check_all, check_connectivity


class TestCheckConnectivity(unittest.TestCase):
    @patch("campsite_monitor.checker.requests.head")
    def test_returns_true_when_reachable(self, mock_head):
        mock_head.return_value = MagicMock(status_code=200)
        self.assertTrue(check_connectivity())

    @patch("campsite_monitor.checker.requests.head", side_effect=ConnectionError("fail"))
    def test_returns_false_on_error(self, mock_head):
        self.assertFalse(check_connectivity())


class TestCheckAll(unittest.TestCase):
    def test_aggregates_results_from_both_sources(self):
        mock_recgov = MagicMock()
        mock_reserveca = MagicMock()
        site_a = {"site": "001", "campground": "Camp A", "url": "u"}
        site_b = {"site": "002", "campground": "Camp B", "url": "u"}
        mock_recgov.check_availability.return_value = [site_a]
        mock_reserveca.check_availability.return_value = [site_b]

        results, errors = check_all(
            [{"name": "Camp A", "id": "1"}],
            [{"name": "Camp B", "facility_id": "2", "place_id": "3"}],
            date(2024, 6, 14), date(2024, 6, 16),
            mock_recgov, mock_reserveca
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(errors, [])

    def test_errors_collected_not_raised(self):
        mock_recgov = MagicMock()
        mock_reserveca = MagicMock()
        mock_recgov.check_availability.side_effect = Exception("fail")
        mock_reserveca.check_availability.return_value = []

        results, errors = check_all(
            [{"name": "Camp A", "id": "1"}],
            [],
            date(2024, 6, 14), date(2024, 6, 16),
            mock_recgov, mock_reserveca
        )
        self.assertEqual(results, [])
        self.assertEqual(errors, ["Camp A"])

    def test_passes_site_type_filter(self):
        mock_recgov = MagicMock()
        mock_reserveca = MagicMock()
        mock_reserveca.check_availability.return_value = []

        cg = {"name": "Camp B", "facility_id": "2", "place_id": "3",
              "filters": {"site_types": ["Campsite"]}}

        check_all([], [cg], date(2024, 6, 14), date(2024, 6, 16),
                  mock_recgov, mock_reserveca)

        _, kwargs = mock_reserveca.check_availability.call_args
        self.assertEqual(kwargs["site_type_filter"], ["Campsite"])
