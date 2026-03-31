import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from campsite_monitor.__main__ import parse_dates, main


class TestDateValidation(unittest.TestCase):
    """Test that invalid date ranges are rejected."""

    def test_checkout_before_checkin(self):
        with self.assertRaises(SystemExit):
            parse_dates(["2024-06-16:2024-06-14"])

    def test_malformed_date_input(self):
        with self.assertRaises(SystemExit):
            parse_dates(["foo:bar"])

    def test_missing_colon_in_date(self):
        with self.assertRaises(SystemExit):
            parse_dates(["2024-06-14"])

    def test_valid_date_range(self):
        result = parse_dates(["2024-06-14:2024-06-16"])
        self.assertEqual(result, [(date(2024, 6, 14), date(2024, 6, 16))])

    def test_multiple_date_ranges(self):
        result = parse_dates(["2024-06-14:2024-06-16", "2024-07-01:2024-07-03"])
        self.assertEqual(len(result), 2)


class TestMainLoopResilience(unittest.TestCase):
    """Test that the main loop survives unexpected errors."""

    @patch("campsite_monitor.__main__.time.sleep")
    @patch("campsite_monitor.__main__.start_status_server")
    @patch("campsite_monitor.__main__.get_campground_info", return_value=[])
    @patch("campsite_monitor.__main__.reserveca")
    @patch("campsite_monitor.__main__.SiteDB")
    @patch("campsite_monitor.__main__.load_config", return_value={"recgov": [], "reserveca": []})
    @patch("campsite_monitor.__main__.check_all", side_effect=RuntimeError("unexpected"))
    @patch("campsite_monitor.__main__.check_connectivity", return_value=True)
    @patch("dotenv.load_dotenv")
    @patch("sys.argv", ["prog", "--dates", "2024-06-14:2024-06-16", "--once", "--no-telegram", "--config", "test.yaml"])
    def test_main_loop_survives_unexpected_error(self, mock_dotenv, mock_conn,
                                                  mock_check_all, mock_config,
                                                  mock_db, mock_rca, mock_info,
                                                  mock_server, mock_sleep):
        mock_rca.CAMPGROUNDS = []
        mock_rca.discover_all_facilities = MagicMock()
        # Should not raise -- the exception guard catches it
        main()


class TestNetworkSkip(unittest.TestCase):
    """Test that the main loop skips cycles when the network is down."""

    @patch("campsite_monitor.__main__.time.sleep")
    @patch("campsite_monitor.__main__.start_status_server")
    @patch("campsite_monitor.__main__.get_campground_info", return_value=[])
    @patch("campsite_monitor.__main__.reserveca")
    @patch("campsite_monitor.__main__.SiteDB")
    @patch("campsite_monitor.__main__.load_config", return_value={"recgov": [], "reserveca": []})
    @patch("campsite_monitor.__main__.check_all")
    @patch("campsite_monitor.__main__.check_connectivity", return_value=False)
    @patch("dotenv.load_dotenv")
    @patch("sys.argv", ["prog", "--dates", "2024-06-14:2024-06-16", "--once", "--no-telegram", "--config", "test.yaml"])
    def test_skips_cycle_when_network_down(self, mock_dotenv, mock_conn,
                                            mock_check_all, mock_config,
                                            mock_db, mock_rca, mock_info,
                                            mock_server, mock_sleep):
        mock_rca.CAMPGROUNDS = []
        mock_rca.discover_all_facilities = MagicMock()
        main()
        mock_check_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
