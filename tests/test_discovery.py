from __future__ import annotations

import json
import unittest

from leadcompass.config import BusinessProfile
from leadcompass.tasks.discovery import discover_prospects


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


if __name__ == "__main__":
    unittest.main()
