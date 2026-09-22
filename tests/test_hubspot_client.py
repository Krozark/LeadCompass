from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import requests

from leadcompass.hubspot_client import HubSpotClient, HubSpotError


def _response(status_code: int = 200, json_data: dict | None = None):
    response = MagicMock()
    response.status_code = status_code
    response.content = b"{}" if json_data is not None else b""
    response.json.return_value = json_data or {}
    if status_code >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    else:
        response.raise_for_status.side_effect = None
    return response


class HubSpotClientInitTests(unittest.TestCase):
    def test_missing_token_raises(self):
        with self.assertRaises(HubSpotError):
            HubSpotClient(token="")

    def test_retry_adapter_mounted_excludes_post_includes_patch(self):
        client = HubSpotClient(token="fake-token")
        adapter = client._session.get_adapter("https://api.hubapi.com/whatever")
        self.assertEqual(adapter.max_retries.total, 3)
        self.assertNotIn("POST", adapter.max_retries.allowed_methods)
        self.assertIn("PATCH", adapter.max_retries.allowed_methods)


class HubSpotClientBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.client = HubSpotClient(token="fake-token")
        self.client._session = MagicMock()

    def test_property_exists_false_on_404(self):
        self.client._session.get.return_value = _response(status_code=404)
        self.assertFalse(self.client._property_exists("leadcompass_score"))

    def test_property_exists_true_on_200(self):
        self.client._session.get.return_value = _response(json_data={"name": "leadcompass_score"})
        self.assertTrue(self.client._property_exists("leadcompass_score"))

    def test_search_contacts_returns_results_and_next_cursor(self):
        self.client._session.request.return_value = _response(
            json_data={"results": [{"id": "1"}], "paging": {"next": {"after": "42"}}}
        )
        results, after = self.client.search_contacts("jean")
        self.assertEqual(results, [{"id": "1"}])
        self.assertEqual(after, "42")

    def test_search_contacts_no_next_page(self):
        self.client._session.request.return_value = _response(json_data={"results": []})
        results, after = self.client.search_contacts("jean")
        self.assertEqual(results, [])
        self.assertIsNone(after)

    def test_get_engagements_sorts_with_null_timestamp_without_crashing(self):
        def fake_request(method, url, timeout=30, **kwargs):
            if "/associations/notes" in url:
                return _response(json_data={"results": [{"toObjectId": "1"}]})
            if "/associations/emails" in url:
                return _response(json_data={"results": []})
            if url.endswith("/notes/1"):
                return _response(
                    json_data={"id": "1", "properties": {"hs_note_body": "hi", "hs_timestamp": None}}
                )
            return _response(json_data={})

        self.client._session.request.side_effect = fake_request
        engagements = self.client.get_engagements("contact-1")
        self.assertEqual(len(engagements), 1)
        self.assertEqual(engagements[0]["engagement_type"], "notes")

    def test_create_note_raises_when_association_fails(self):
        def fake_request(method, url, timeout=30, **kwargs):
            if method == "POST" and url.endswith("/notes"):
                return _response(json_data={"id": "note-1"})
            if method == "PUT":
                return _response(status_code=404)
            return _response(json_data={})

        self.client._session.request.side_effect = fake_request
        with self.assertRaises(requests.HTTPError):
            self.client.create_note("contact-1", "hello")


if __name__ == "__main__":
    unittest.main()
