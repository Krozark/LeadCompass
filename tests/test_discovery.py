from __future__ import annotations

import json
import unittest

from leadcompass.config import BusinessProfile
from leadcompass.tasks.discovery import discover_prospects, split_known_leads


class FakeBackend:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self._response


def _payload() -> list[dict]:
    return [
        {
            "name": "Marie Martin",
            "organization": "Festival du Ponant",
            "role": "Directrice de programmation",
            "email": "",
            "website": "https://festival-ponant.fr",
            "why_relevant": "Festival jazz en Bretagne",
        }
    ]


class DiscoverProspectsTests(unittest.TestCase):
    def test_parses_json_array(self):
        backend = FakeBackend(json.dumps(_payload(), ensure_ascii=False))
        results = discover_prospects("festivals jazz en Bretagne", BusinessProfile(), backend)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Marie Martin")
        self.assertEqual(results[0]["website"], "https://festival-ponant.fr")

    def test_handles_markdown_fenced_json(self):
        fenced = "Voici les résultats :\n```json\n" + json.dumps(_payload()) + "\n```"
        backend = FakeBackend(fenced)
        results = discover_prospects("guide", BusinessProfile(), backend)
        self.assertEqual(len(results), 1)

    def test_normalizes_missing_fields_and_drops_non_dict_items(self):
        raw = json.dumps([{"name": "Marie Martin"}, "pas un dict", {"role": "Influenceur"}])
        backend = FakeBackend(raw)
        results = discover_prospects("guide", BusinessProfile(), backend)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["email"], "")
        self.assertEqual(results[1]["name"], "")

    def test_raises_when_no_json_array(self):
        backend = FakeBackend("Désolé, je n'ai rien trouvé.")
        with self.assertRaises(ValueError):
            discover_prospects("guide", BusinessProfile(), backend)

    def test_raises_on_invalid_json(self):
        backend = FakeBackend("[{name: malformed}")
        with self.assertRaises(ValueError):
            discover_prospects("guide", BusinessProfile(), backend)

    def test_prompt_includes_guide_and_count(self):
        backend = FakeBackend(json.dumps(_payload()))
        discover_prospects("influenceurs data B2B", BusinessProfile(), backend, count=7)
        system, user = backend.calls[0]
        self.assertIn("recherche", system.lower())
        self.assertIn("influenceurs data B2B", user)
        self.assertIn("7", user)

    def test_prompt_lists_known_identities(self):
        backend = FakeBackend(json.dumps(_payload()))
        discover_prospects(
            "guide", BusinessProfile(), backend, known_identities=["Festival du Ponant", "Marie Martin"]
        )
        _, user = backend.calls[0]
        self.assertIn("Festival du Ponant", user)
        self.assertIn("Marie Martin", user)


class SplitKnownLeadsTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            {
                "name": "Marie Martin",
                "organization": "Festival du Ponant",
                "role": "Directrice",
                "email": "marie@ponant.fr",
                "website": "",
                "why_relevant": "",
            },
            {
                "name": "Nouveau Contact",
                "organization": "Inconnu SARL",
                "role": "CEO",
                "email": "ceo@inconnu.fr",
                "website": "",
                "why_relevant": "",
            },
        ]

    def test_hides_lead_matching_known_email(self):
        kept, hidden = split_known_leads(self.results, {"marie@ponant.fr"}, set())
        self.assertEqual(hidden, 1)
        self.assertEqual([lead["name"] for lead in kept], ["Nouveau Contact"])

    def test_hides_lead_matching_known_name_or_organization(self):
        kept, hidden = split_known_leads(self.results, set(), {"marie martin", "festival du ponant"})
        self.assertEqual(hidden, 1)
        self.assertEqual([lead["name"] for lead in kept], ["Nouveau Contact"])

    def test_matching_is_case_and_whitespace_insensitive(self):
        kept, hidden = split_known_leads(self.results, {"  MARIE@Ponant.FR "}, {"  nouveau   contact "})
        self.assertEqual(hidden, 2)
        self.assertEqual(kept, [])

    def test_keeps_everything_when_nothing_known(self):
        kept, hidden = split_known_leads(self.results, set(), set())
        self.assertEqual(hidden, 0)
        self.assertEqual(kept, self.results)

    def test_empty_fields_never_match(self):
        results = [
            {"name": "", "organization": "", "role": "", "email": "", "website": "", "why_relevant": ""}
        ]
        kept, hidden = split_known_leads(results, {""}, {""})
        self.assertEqual(hidden, 0)
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
