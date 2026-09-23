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

    def test_list_contacts_returns_results_and_next_cursor(self):
        self.client._session.request.return_value = _response(
            json_data={"results": [{"id": "1"}, {"id": "2"}], "paging": {"next": {"after": "20"}}}
        )
        results, after = self.client.list_contacts()
        self.assertEqual(len(results), 2)
        self.assertEqual(after, "20")

    def test_list_contacts_no_next_page(self):
        self.client._session.request.return_value = _response(json_data={"results": [{"id": "1"}]})
        results, after = self.client.list_contacts()
        self.assertEqual(results, [{"id": "1"}])
        self.assertIsNone(after)

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

    def test_create_email_log_outgoing(self):
        calls = []

        def fake_request(method, url, timeout=30, **kwargs):
            calls.append((method, url))
            if method == "POST" and url.endswith("/emails"):
                return _response(json_data={"id": "email-1"})
            return _response(json_data={})

        self.client._session.request.side_effect = fake_request
        self.client.create_email_log("contact-1", "body", "EMAIL", "Sujet")
        methods = [c[0] for c in calls]
        self.assertIn("POST", methods)
        self.assertIn("PUT", methods)
        self.assertIn("/emails", calls[0][1])

    def test_create_email_log_raises_when_association_fails(self):
        def fake_request(method, url, timeout=30, **kwargs):
            if method == "POST" and url.endswith("/emails"):
                return _response(json_data={"id": "email-1"})
            if method == "PUT":
                return _response(status_code=404)
            return _response(json_data={})

        self.client._session.request.side_effect = fake_request
        with self.assertRaises(requests.HTTPError):
            self.client.create_email_log("contact-1", "body", "INCOMING_EMAIL")

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

    def test_create_contact_posts_properties(self):
        self.client._session.request.return_value = _response(
            status_code=201, json_data={"id": "contact-9", "properties": {"email": "a@b.c"}}
        )
        contact = self.client.create_contact({"email": "a@b.c"})
        self.assertEqual(contact["id"], "contact-9")
        method, url = self.client._session.request.call_args.args
        self.assertEqual(method, "POST")
        self.assertTrue(url.endswith("/crm/v3/objects/contacts"))
        self.assertEqual(
            self.client._session.request.call_args.kwargs["json"]["properties"]["email"], "a@b.c"
        )

    def test_create_contact_duplicate_email_raises_hubspot_error(self):
        response = MagicMock()
        response.status_code = 409
        response.content = b""
        response.raise_for_status.side_effect = requests.HTTPError("409 conflict", response=response)
        self.client._session.request.return_value = response
        with self.assertRaises(HubSpotError):
            self.client.create_contact({"email": "dup@example.com"})


if __name__ == "__main__":
    unittest.main()
