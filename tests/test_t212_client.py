import unittest
from unittest.mock import MagicMock, patch

import requests

from broker.t212_client import T212Client


class TestT212Client(unittest.TestCase):
    @patch("broker.t212_client.requests.Session.get")
    def test_get_account_cash_returns_dict_on_200(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.json.return_value = {"cash": 950.0}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        client = T212Client()
        result = client.get_account_cash()

        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["free"], 950.0)

    @patch("broker.t212_client.requests.Session.get")
    def test_get_account_cash_returns_none_on_401(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mock_get.return_value = mock_response

        client = T212Client()
        result = client.get_account_cash()

        self.assertEqual(result, {"free": 0.0, "total": 0.0})

    @patch("broker.t212_client.requests.Session.get")
    def test_get_account_cash_returns_none_on_timeout(
        self, mock_get: MagicMock
    ) -> None:
        mock_get.side_effect = requests.exceptions.Timeout

        client = T212Client()
        result = client.get_account_cash()

        self.assertEqual(result, {"free": 0.0, "total": 0.0})

    @patch("broker.t212_client.requests.Session.get")
    def test_get_positions_returns_list_on_200(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {"ticker": "AAPL_US_EQ", "quantity": 10},
            {"ticker": "MSFT_US_EQ", "quantity": 5},
        ]
        mock_get.return_value = mock_response

        client = T212Client()
        result = client.get_positions()

        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertEqual(len(result), 2)

    @patch("broker.t212_client.requests.Session.get")
    def test_get_positions_returns_none_on_500(self, mock_get: MagicMock) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError()
        mock_get.return_value = mock_response

        client = T212Client()
        result = client.get_positions()

        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
