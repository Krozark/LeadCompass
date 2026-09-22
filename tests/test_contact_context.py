from __future__ import annotations

import unittest

from leadcompass.contact_context import build_contact_context


class BuildContactContextTests(unittest.TestCase):
    def test_includes_contact_fields(self):
        contact = {
            "properties": {
                "firstname": "Jean",
                "lastname": "Dupont",
                "email": "j@x.com",
                "company": "Acme",
                "jobtitle": "CEO",
            }
        }
        text = build_contact_context(contact, [])
        for expected in ("Jean", "Dupont", "j@x.com", "Acme", "CEO"):
            self.assertIn(expected, text)

    def test_null_engagement_body_does_not_crash(self):
        contact = {"properties": {}}
        engagements = [
            {"properties": {"hs_note_body": None, "hs_email_text": None}, "engagement_type": "emails"}
        ]
        text = build_contact_context(contact, engagements)
        self.assertIn("[emails]", text)

    def test_prefers_note_body_over_email_text(self):
        contact = {"properties": {}}
        engagements = [{"properties": {"hs_note_body": "hello note"}, "engagement_type": "notes"}]
        text = build_contact_context(contact, engagements)
        self.assertIn("hello note", text)

    def test_truncates_long_body_to_300_chars(self):
        contact = {"properties": {}}
        engagements = [{"properties": {"hs_note_body": "x" * 500}, "engagement_type": "notes"}]
        text = build_contact_context(contact, engagements)
        self.assertIn("x" * 300, text)
        self.assertNotIn("x" * 301, text)


if __name__ == "__main__":
    unittest.main()
