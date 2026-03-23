import json
import os
import tempfile
import time
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


def make_place_response(facilities_dict):
    """Helper to build a mock place API response."""
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "SelectedPlace": {
            "Facilities": facilities_dict,
        }
    }
    return resp


class TestCheckAvailability(unittest.TestCase):
    campground = {"name": "Test Park", "place_id": "100", "facility_id": "200"}

    @patch("reserveca.requests.post")
    def test_mixed_availability(self, mock_post):
        mock_post.return_value = make_response({
            "u1": {
                "Name": "Site A",
                "Slices": {
                    "2024-06-14T00:00:00": {"IsFree": True},
                    "2024-06-15T00:00:00": {"IsFree": True},
                },
            },
            "u2": {
                "Name": "Site B",
                "Slices": {
                    "2024-06-14T00:00:00": {"IsFree": True},
                    "2024-06-15T00:00:00": {"IsFree": False},
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


SAMPLE_FACILITIES = {
    "611": {"FacilityId": 611, "Name": "South Camp"},
    "767": {"FacilityId": 767, "Name": "Main Camp"},
}

# Dict keys differ from FacilityId values (like Hearst San Simeon)
MISMATCHED_FACILITIES = {
    "1": {"FacilityId": 789, "Name": "Upper Section"},
    "4": {"FacilityId": 787, "Name": "Washburn"},
}


class TestDiscoverFacilities(unittest.TestCase):
    @patch("reserveca.requests.post")
    def test_discover_returns_facility_list(self, mock_post):
        mock_post.return_value = make_place_response(SAMPLE_FACILITIES)

        result = reserveca.discover_facilities("690")

        self.assertEqual(len(result), 2)
        ids = {f["facility_id"] for f in result}
        self.assertEqual(ids, {"611", "767"})
        names = {f["facility_name"] for f in result}
        self.assertEqual(names, {"South Camp", "Main Camp"})

    @patch("reserveca.requests.post")
    def test_discover_uses_facility_id_not_dict_key(self, mock_post):
        mock_post.return_value = make_place_response(MISMATCHED_FACILITIES)

        result = reserveca.discover_facilities("713")

        ids = {f["facility_id"] for f in result}
        self.assertEqual(ids, {"789", "787"})
        self.assertNotIn("1", ids)
        self.assertNotIn("4", ids)

    @patch("reserveca.requests.post", side_effect=Exception("timeout"))
    def test_discover_raises_on_failure(self, mock_post):
        with self.assertRaises(ConnectionError):
            reserveca.discover_facilities("690")


class TestDiscoverAllFacilities(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.cache_file = os.path.join(self.tmpdir, "facility_cache.json")
        self._orig_cache = reserveca.CACHE_FILE
        self._orig_parks = reserveca.PARKS
        self._orig_campgrounds = reserveca.CAMPGROUNDS
        reserveca.CACHE_FILE = self.cache_file
        reserveca.PARKS = [{"name": "Test Park", "place_id": "690"}]
        reserveca.CAMPGROUNDS = []

    def tearDown(self):
        reserveca.CACHE_FILE = self._orig_cache
        reserveca.PARKS = self._orig_parks
        reserveca.CAMPGROUNDS = self._orig_campgrounds
        if os.path.exists(self.cache_file):
            os.remove(self.cache_file)
        os.rmdir(self.tmpdir)

    @patch("reserveca.requests.post")
    def test_api_success_populates_campgrounds_and_cache(self, mock_post):
        mock_post.return_value = make_place_response(SAMPLE_FACILITIES)

        reserveca.discover_all_facilities()

        self.assertEqual(len(reserveca.CAMPGROUNDS), 2)
        names = {cg["name"] for cg in reserveca.CAMPGROUNDS}
        self.assertIn("Test Park \u2014 South Camp", names)
        self.assertIn("Test Park \u2014 Main Camp", names)

        # Cache was written
        self.assertTrue(os.path.exists(self.cache_file))
        with open(self.cache_file) as f:
            cache = json.load(f)
        self.assertIn("690", cache)

    @patch("reserveca.requests.post")
    def test_fresh_cache_skips_api(self, mock_post):
        # Pre-populate cache
        cache = {
            "690": {
                "facilities": [
                    {"facility_id": "611", "facility_name": "South Camp"},
                ],
                "timestamp": time.time(),
            }
        }
        with open(self.cache_file, "w") as f:
            json.dump(cache, f)

        reserveca.discover_all_facilities()

        mock_post.assert_not_called()
        self.assertEqual(len(reserveca.CAMPGROUNDS), 1)
        self.assertEqual(reserveca.CAMPGROUNDS[0]["name"], "Test Park \u2014 South Camp")

    @patch("reserveca.requests.post", side_effect=Exception("timeout"))
    def test_api_failure_uses_stale_cache(self, mock_post):
        # Pre-populate stale cache (old timestamp)
        cache = {
            "690": {
                "facilities": [
                    {"facility_id": "767", "facility_name": "Main Camp"},
                ],
                "timestamp": time.time() - 200000,
            }
        }
        with open(self.cache_file, "w") as f:
            json.dump(cache, f)

        reserveca.discover_all_facilities()

        self.assertEqual(len(reserveca.CAMPGROUNDS), 1)
        self.assertEqual(reserveca.CAMPGROUNDS[0]["facility_id"], "767")

    @patch("reserveca.requests.post", side_effect=Exception("timeout"))
    def test_api_failure_no_cache_skips_park(self, mock_post):
        reserveca.discover_all_facilities()

        self.assertEqual(len(reserveca.CAMPGROUNDS), 0)

    def test_manual_facility_ids_skip_discovery(self):
        reserveca.PARKS = [
            {"name": "Test Park", "place_id": "690", "facility_ids": ["767"]},
        ]

        with patch("reserveca.requests.post") as mock_post:
            reserveca.discover_all_facilities()

        mock_post.assert_not_called()
        self.assertEqual(len(reserveca.CAMPGROUNDS), 1)
        self.assertEqual(reserveca.CAMPGROUNDS[0]["facility_id"], "767")
        self.assertEqual(reserveca.CAMPGROUNDS[0]["name"], "Test Park")

    @patch("reserveca.requests.post")
    def test_name_format(self, mock_post):
        mock_post.return_value = make_place_response(SAMPLE_FACILITIES)

        reserveca.discover_all_facilities()

        for cg in reserveca.CAMPGROUNDS:
            self.assertIn(" \u2014 ", cg["name"])
            self.assertTrue(cg["name"].startswith("Test Park \u2014 "))


if __name__ == "__main__":
    unittest.main()
