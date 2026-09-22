from __future__ import annotations

import json
import unittest

from leadcompass.config import BusinessProfile
from leadcompass.tasks.profile_generation import generate_profile_from_folders


class FakeExploringBackend:
    def __init__(self, response: str):
        self._response = response
        self.calls: list[tuple[str, str, list[str]]] = []

    def explore(self, system: str, user: str, directories: list[str], **kwargs) -> str:
        self.calls.append((system, user, directories))
        return self._response


class GenerateProfileFromFoldersTests(unittest.TestCase):
    def test_parses_generated_profile(self):
        payload = {
            "name": "Acme",
            "product_description": "Widgets",
            "target_customer": "SMBs",
            "value_proposition": "Cheap",
            "tone": "direct",
            "scoring_criteria": [{"name": "Fit", "description": "d", "weight": 2}],
        }
        backend = FakeExploringBackend(json.dumps(payload))
        result = generate_profile_from_folders(["/tmp/docs"], BusinessProfile(), backend)
        self.assertEqual(result.name, "Acme")
        self.assertEqual(len(result.scoring_criteria), 1)
        self.assertEqual(result.scoring_criteria[0].weight, 2)

    def test_includes_existing_profile_in_prompt_when_configured(self):
        backend = FakeExploringBackend('{"name": "Acme", "product_description": "x"}')
        existing = BusinessProfile(name="Old", product_description="Old desc")
        generate_profile_from_folders(["/tmp/docs"], existing, backend)
        _, user_prompt, directories = backend.calls[0]
        self.assertIn("Old", user_prompt)
        self.assertEqual(directories, ["/tmp/docs"])

    def test_skips_existing_profile_context_when_not_configured(self):
        backend = FakeExploringBackend('{"name": "Acme", "product_description": "x"}')
        generate_profile_from_folders(["/tmp/docs"], BusinessProfile(), backend)
        _, user_prompt, _ = backend.calls[0]
        self.assertNotIn("Profil actuel", user_prompt)


if __name__ == "__main__":
    unittest.main()
