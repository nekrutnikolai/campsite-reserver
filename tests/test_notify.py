import unittest
from datetime import date
from unittest.mock import patch, MagicMock

import notify


class TestFormatAlert(unittest.TestCase):
    def test_format_alert(self):
        result = notify.format_alert("Kirk Creek", "042", "https://example.com/book")
        self.assertIn("*Kirk Creek*", result)
        self.assertIn("Site 042", result)
        self.assertIn("[Book now](https://example.com/book)", result)

    def test_format_alert_with_park_url(self):
        result = notify.format_alert(
            "Kirk Creek", "042", "https://example.com/book",
            park_url="https://example.com/park",
        )
        self.assertIn("[Book now](https://example.com/book)", result)
        self.assertIn("[Browse facility](https://example.com/park)", result)

    def test_format_alert_with_site_type(self):
        result = notify.format_alert(
            "Kirk Creek", "042", "https://example.com/book",
            site_type="Standard Campsite",
        )
        self.assertIn("*Kirk Creek*", result)
        self.assertIn("Site 042", result)
        self.assertIn("Standard Campsite", result)
        self.assertIn("[Book now](https://example.com/book)", result)

    def test_format_alert_without_site_type(self):
        result = notify.format_alert("Kirk Creek", "042", "https://example.com/book")
        self.assertIn("*Kirk Creek*", result)
        self.assertIn("Site 042", result)
        self.assertIn("[Book now](https://example.com/book)", result)
        # Verify no extra newline between "available!" and "[Book now]"
        self.assertIn("available!\n[Book now]", result)


class TestFormatGone(unittest.TestCase):
    def test_format_gone(self):
        result = notify.format_gone(
            "Kirk Creek", "042", date(2024, 6, 14), date(2024, 6, 16),
        )
        self.assertIn("Kirk Creek", result)
        self.assertIn("042", result)
        self.assertIn("2024-06-14", result)
        self.assertIn("2024-06-16", result)
        self.assertIn("\u274c", result)


class TestEscapeMd(unittest.TestCase):
    def test_escape_md(self):
        result = notify.escape_md("Camp_Site *A* `code` [1]")
        self.assertIn("\\_", result)
        self.assertIn("\\*", result)
        self.assertIn("\\`", result)
        self.assertIn("\\[", result)


class TestSendTelegram(unittest.TestCase):
    @patch("notify.requests.post")
    def test_success(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        result = notify.send_telegram("tok", "123", "hello")
        self.assertTrue(result)
        mock_post.assert_called_once()

    @patch("notify.requests.post")
    def test_http_error(self, mock_post):
        mock_post.return_value = MagicMock(status_code=400, text="Bad Request")
        result = notify.send_telegram("tok", "123", "hello")
        self.assertFalse(result)

    @patch("notify.requests.post", side_effect=ConnectionError("fail"))
    def test_connection_error(self, mock_post):
        result = notify.send_telegram("tok", "123", "hello")
        self.assertFalse(result)

    @patch("notify.requests.post")
    def test_send_telegram_timeout(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        notify.send_telegram("tok", "123", "hello")
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["timeout"], 15)


if __name__ == "__main__":
    unittest.main()
