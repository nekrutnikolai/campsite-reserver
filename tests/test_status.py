import unittest

from campsite_monitor.status_server import status


class TestStatusDict(unittest.TestCase):
    def test_initial_status_structure(self):
        """Verify all expected keys exist in the status dict."""
        expected_keys = {"started", "last_check", "checks", "failures",
                        "failed_sources", "sites_found", "total_tracked",
                        "date_ranges", "campgrounds", "recent_finds"}
        self.assertEqual(set(status.keys()), expected_keys)

    def test_status_json_serializable(self):
        import json
        json.dumps(status)  # Should not raise
