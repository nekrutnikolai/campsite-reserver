import unittest
from datetime import date
from unittest.mock import patch, MagicMock

import reserveca


def make_response(units):
    """Helper to build a mock ReserveCalifornia API response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"Facility": {"Units": units}}
    return resp


class TestCheckAvailability(unittest.TestCase):
    campground = {"name": "Test Park", "place_id": "100", "facility_id": "200"}

    @patch("reserveca.requests.post")
    def test_mixed_availability(self, mock_post):
        mock_post.return_value = make_response({
            "u1": {
                "Name": "Site A",
                "Slices": {
                    "06/14/2024": {"IsFree": True},
                    "06/15/2024": {"IsFree": True},
                },
            },
            "u2": {
                "Name": "Site B",
                "Slices": {
                    "06/14/2024": {"IsFree": True},
                    "06/15/2024": {"IsFree": False},
                },
            },
        })

        result = reserveca.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["site"], "Site A")
        self.assertEqual(result[0]["campground"], "Test Park")

    @patch("reserveca.requests.post", side_effect=Exception("timeout"))
    def test_error_returns_empty(self, mock_post):
        result = reserveca.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 16)
        )
        self.assertEqual(result, [])

    @patch("reserveca.requests.post")
    def test_date_format_in_request(self, mock_post):
        mock_post.return_value = make_response({})

        reserveca.check_availability(
            self.campground, date(2024, 6, 14), date(2024, 6, 16)
        )

        call_body = mock_post.call_args[1]["json"]
        self.assertEqual(call_body["StartDate"], "06-14-2024")
        self.assertEqual(call_body["EndDate"], "06-16-2024")
        self.assertEqual(call_body["FacilityId"], 200)


if __name__ == "__main__":
    unittest.main()
