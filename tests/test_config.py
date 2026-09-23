from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from leadcompass import config
from leadcompass.config import (
    BusinessProfile,
    LLMBackendConfig,
    ScoringCriterion,
    load_business_profile,
    load_llm_backends,
    save_business_profile,
    save_llm_backends,
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


class LlmChoiceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_dir = Path(tmp.name)

        for name, value in (
            ("CONFIG_DIR", tmp_dir),
            ("SETTINGS_PATH", tmp_dir / "settings.yaml"),
        ):
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_missing_settings_returns_empty(self):
        self.assertEqual(config.load_llm_choice(), "")

    def test_save_then_load_round_trip(self):
        config.save_llm_choice("GLM")
        self.assertEqual(config.load_llm_choice(), "GLM")

    def test_save_overwrites_previous_choice(self):
        config.save_llm_choice("Claude")
        config.save_llm_choice("GLM")
        self.assertEqual(config.load_llm_choice(), "GLM")

    def test_save_preserves_unrelated_settings(self):
        with open(config.SETTINGS_PATH, "w", encoding="utf-8") as f:
            f.write("theme: dark\n")
        config.save_llm_choice("GLM")
        self.assertEqual(config.load_settings().get("theme"), "dark")


class LlmBackendsTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        tmp_dir = Path(tmp.name)

        for name, value in (
            ("CONFIG_DIR", tmp_dir),
            ("SETTINGS_PATH", tmp_dir / "settings.yaml"),
        ):
            patcher = patch.object(config, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_defaults_without_settings(self):
        with patch.object(config.shutil, "which", return_value=None):
            backends = load_llm_backends()
        self.assertEqual(backends, [LLMBackendConfig("Claude", config.CLAUDE_CLI_PATH)])

    def test_defaults_add_glm_when_claude_zai_detected(self):
        with patch.object(
            config.shutil, "which", side_effect=lambda p: f"/usr/bin/{p}" if p == "claude-zai" else None
        ):
            backends = load_llm_backends()
        self.assertEqual(
            backends,
            [LLMBackendConfig("Claude", config.CLAUDE_CLI_PATH), LLMBackendConfig("GLM", "claude-zai")],
        )

    def test_save_then_load_round_trip(self):
        save_llm_backends(
            [LLMBackendConfig("Claude", "claude"), LLMBackendConfig("Zai", "/home/me/bin/claude-zai")]
        )
        self.assertEqual(
            load_llm_backends(),
            [LLMBackendConfig("Claude", "claude"), LLMBackendConfig("Zai", "/home/me/bin/claude-zai")],
        )
        # le choix enregistré et les autres réglages survivent à l'écriture
        self.assertEqual(
            config.load_settings().get("llm_backends")[0], {"name": "Claude", "cli_path": "claude"}
        )

    def test_saved_backends_win_over_defaults(self):
        save_llm_backends([LLMBackendConfig("Perso", "/opt/mon-claude")])
        with patch.object(config.shutil, "which", return_value="/usr/bin/claude-zai"):
            self.assertEqual(load_llm_backends(), [LLMBackendConfig("Perso", "/opt/mon-claude")])


if __name__ == "__main__":
    unittest.main()
