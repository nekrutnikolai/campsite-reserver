import unittest
from datetime import date
from unittest.mock import patch, MagicMock

import recgov


def make_response(campsites):
    """Helper to build a mock Recreation.gov API response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"campsites": campsites}
    return resp


class TestCheckAvailability(unittest.TestCase):
    campground = {"name": "Test Camp", "id": "12345"}

    @patch("recgov.UserAgent")
    @patch("recgov.requests.get")
    def test_mixed_availability(self, mock_get, mock_ua):
        mock_ua.return_value.random = "TestAgent"
        mock_get.return_value = make_response({
            "site1": {
                "site": "001",
                "availabilities": {
                    "2024-06-14T00:00:00Z": "Available",
                    "2024-06-15T00:00:00Z": "Available",
                },
            },
            "site2": {
                "site": "002",
                "availabilities": {
                    "2024-06-14T00:00:00Z": "Reserved",
                    "2024-06-15T00:00:00Z": "Available",
                },
            },
        })

        result = recgov.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["site"], "001")
        self.assertEqual(result[0]["campground"], "Test Camp")

    @patch("recgov.UserAgent")
    @patch("recgov.requests.get")
    def test_one_night_reserved(self, mock_get, mock_ua):
        mock_ua.return_value.random = "TestAgent"
        mock_get.return_value = make_response({
            "site1": {
                "site": "001",
                "availabilities": {
                    "2024-06-14T00:00:00Z": "Available",
                    "2024-06-15T00:00:00Z": "Reserved",
                    "2024-06-16T00:00:00Z": "Available",
                },
            },
        })

        result = recgov.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 17)
        )
        self.assertEqual(len(result), 0)

    @patch("recgov.UserAgent")
    @patch("recgov.requests.get")
    def test_multi_month_query(self, mock_get, mock_ua):
        mock_ua.return_value.random = "TestAgent"
        # Two months queried: June and July
        resp_june = make_response({
            "site1": {
                "site": "001",
                "availabilities": {"2024-06-30T00:00:00Z": "Available"},
            },
        })
        resp_july = make_response({
            "site1": {
                "site": "001",
                "availabilities": {"2024-07-01T00:00:00Z": "Available"},
            },
        })
        mock_get.side_effect = [resp_june, resp_july]

        result = recgov.check_availability(
            self.campground, date(2024, 6, 30), date(2024, 7, 2)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(mock_get.call_count, 2)

    @patch("recgov.UserAgent")
    @patch("recgov.requests.get", side_effect=Exception("network error"))
    def test_request_error(self, mock_get, mock_ua):
        mock_ua.return_value.random = "TestAgent"
        result = recgov.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(result, [])

    @patch("recgov.UserAgent")
    @patch("recgov.requests.get")
    def test_empty_response(self, mock_get, mock_ua):
        mock_ua.return_value.random = "TestAgent"
        mock_get.return_value = make_response({})

        result = recgov.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
