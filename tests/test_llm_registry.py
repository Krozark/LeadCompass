from __future__ import annotations

import unittest
from unittest.mock import patch

from leadcompass.llm import registry
from leadcompass.llm.claude_cli import ClaudeCLIBackend
from leadcompass.llm.glm import GLMBackend


class ConfiguredBackendsTests(unittest.TestCase):
    def test_empty_without_cli_or_api_key(self):
        with (
            patch.object(registry, "claude_cli_available", return_value=False),
            patch.object(registry, "ZAI_API_KEY", ""),
        ):
            self.assertEqual(registry.configured_backends(), {})

    def test_claude_registered_when_cli_available(self):
        with (
            patch.object(registry, "claude_cli_available", return_value=True),
            patch.object(registry, "ZAI_API_KEY", ""),
        ):
            backends = registry.configured_backends()
        self.assertEqual(list(backends), [ClaudeCLIBackend.name])
        self.assertIsInstance(backends[ClaudeCLIBackend.name](), ClaudeCLIBackend)

    def test_glm_registered_when_api_key_set(self):
        with (
            patch.object(registry, "claude_cli_available", return_value=False),
            patch.object(registry, "ZAI_API_KEY", "sk-test"),
        ):
            backends = registry.configured_backends()
        self.assertEqual(list(backends), [GLMBackend.name])
        self.assertIsInstance(backends[GLMBackend.name](), GLMBackend)


class DefaultBackendNameTests(unittest.TestCase):
    def test_prefers_saved_choice_when_available(self):
        with (
            patch.object(registry, "claude_cli_available", return_value=True),
            patch.object(registry, "ZAI_API_KEY", "sk-test"),
            patch.object(registry, "load_llm_choice", return_value=GLMBackend.name),
        ):
            self.assertEqual(registry.default_backend_name(), GLMBackend.name)

    def test_falls_back_to_first_available_when_saved_unavailable(self):
        with (
            patch.object(registry, "claude_cli_available", return_value=True),
            patch.object(registry, "ZAI_API_KEY", ""),
            patch.object(registry, "load_llm_choice", return_value="GPT"),
        ):
            self.assertEqual(registry.default_backend_name(), ClaudeCLIBackend.name)

    def test_empty_when_nothing_configured(self):
        with (
            patch.object(registry, "claude_cli_available", return_value=False),
            patch.object(registry, "ZAI_API_KEY", ""),
        ):
            self.assertEqual(registry.default_backend_name(), "")


class GetBackendTests(unittest.TestCase):
    def test_returns_instance(self):
        with patch.object(registry, "claude_cli_available", return_value=True):
            self.assertIsInstance(registry.get_backend(ClaudeCLIBackend.name), ClaudeCLIBackend)

    def test_rejects_unknown_name(self):
        with self.assertRaises(KeyError):
            registry.get_backend("Inconnu")


if __name__ == "__main__":
    unittest.main()
