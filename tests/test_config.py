from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leadcompass import config
from leadcompass.config import (
    BusinessProfile,
    ScoringCriterion,
    load_business_profile,
    save_business_profile,
)


class BusinessProfileTests(unittest.TestCase):
    def test_to_dict_from_dict_round_trip(self):
        profile = BusinessProfile(
            name="Acme",
            product_description="Widgets",
            target_customer="SMBs",
            value_proposition="Cheaper widgets",
            tone="direct",
            scoring_criteria=[ScoringCriterion("Fit", "Sector fit", 2.0)],
        )
        self.assertEqual(BusinessProfile.from_dict(profile.to_dict()), profile)

    def test_is_configured(self):
        self.assertFalse(BusinessProfile().is_configured)
        self.assertTrue(BusinessProfile(name="Acme", product_description="Widgets").is_configured)

    def test_max_score(self):
        profile = BusinessProfile(
            scoring_criteria=[ScoringCriterion("A", "a", 1), ScoringCriterion("B", "b", 3)]
        )
        self.assertEqual(profile.max_score(), 20)

    def test_max_score_default_when_no_criteria(self):
        self.assertEqual(BusinessProfile().max_score(), 1.0)

    def test_to_prompt_context_contains_fields(self):
        text = BusinessProfile(name="Acme", product_description="Widgets", tone="direct").to_prompt_context()
        self.assertIn("Acme", text)
        self.assertIn("Widgets", text)
        self.assertIn("direct", text)


class LoadSaveBusinessProfileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_dir = Path(tmp.name)

        for name, value in (
            ("CONFIG_DIR", tmp_dir),
            ("PROFILE_PATH", tmp_dir / "business_profile.yaml"),
            ("PROFILE_EXAMPLE_PATH", tmp_dir / "business_profile.example.yaml"),
        ):
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_load_missing_returns_empty_profile(self):
        self.assertEqual(load_business_profile(), BusinessProfile())

    def test_save_then_load_round_trip(self):
        profile = BusinessProfile(
            name="Acme",
            product_description="Widgets",
            target_customer="SMBs",
            value_proposition="Cheaper widgets",
            tone="direct",
            scoring_criteria=[ScoringCriterion("Fit", "Sector fit", 2.0)],
        )
        save_business_profile(profile)
        self.assertEqual(load_business_profile(), profile)


if __name__ == "__main__":
    unittest.main()
