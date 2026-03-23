import unittest
from unittest.mock import patch, MagicMock

import notify


class TestFormatAlert(unittest.TestCase):
    def test_format_alert(self):
        result = notify.format_alert("Kirk Creek", "042", "https://example.com/book")
        self.assertIn("*Kirk Creek*", result)
        self.assertIn("Site 042", result)
        self.assertIn("[Book now](https://example.com/book)", result)


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


if __name__ == "__main__":
    unittest.main()
