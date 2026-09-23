from __future__ import annotations

import unittest
from unittest.mock import patch

from leadcompass.config import LLMBackendConfig
from leadcompass.llm import registry
from leadcompass.llm.claude_cli import ClaudeCLIBackend


def _backends(*configs: LLMBackendConfig):
    return patch.object(registry, "load_llm_backends", return_value=list(configs))


class ConfiguredBackendsTests(unittest.TestCase):
    def test_only_registers_backends_whose_binary_is_detected(self):
        with (
            _backends(
                LLMBackendConfig("Claude", "/bin/claude"),
                LLMBackendConfig("Fantôme", "binaire-inexistant"),
            ),
            patch.object(registry.shutil, "which", side_effect=lambda p: p if p == "/bin/claude" else None),
        ):
            self.assertEqual(registry.configured_backends(), {"Claude": "/bin/claude"})

    def test_empty_when_nothing_detected(self):
        with (
            _backends(LLMBackendConfig("Claude", "claude")),
            patch.object(registry.shutil, "which", return_value=None),
        ):
            self.assertEqual(registry.configured_backends(), {})


class DefaultBackendNameTests(unittest.TestCase):
    def test_prefers_saved_choice_when_available(self):
        with (
            _backends(
                LLMBackendConfig("Claude", "/bin/claude"),
                LLMBackendConfig("GLM", "/bin/claude-zai"),
            ),
            patch.object(registry.shutil, "which", return_value="/usr/bin/whatever"),
            patch.object(registry, "load_llm_choice", return_value="GLM"),
        ):
            self.assertEqual(registry.default_backend_name(), "GLM")

    def test_falls_back_to_first_available_when_saved_unavailable(self):
        with (
            _backends(
                LLMBackendConfig("Claude", "/bin/claude"),
                LLMBackendConfig("GLM", "binaire-inexistant"),
            ),
            patch.object(registry.shutil, "which", side_effect=lambda p: p if p == "/bin/claude" else None),
            patch.object(registry, "load_llm_choice", return_value="GLM"),
        ):
            self.assertEqual(registry.default_backend_name(), "Claude")

    def test_empty_when_nothing_detected(self):
        with (
            _backends(LLMBackendConfig("Claude", "claude")),
            patch.object(registry.shutil, "which", return_value=None),
        ):
            self.assertEqual(registry.default_backend_name(), "")


class GetBackendTests(unittest.TestCase):
    def test_builds_backend_with_registered_cli_path_and_name(self):
        with (
            _backends(LLMBackendConfig("GLM", "/bin/claude-zai")),
            patch.object(registry.shutil, "which", return_value="/usr/bin/whatever"),
        ):
            backend = registry.get_backend("GLM", max_turns=15, timeout=600)
        self.assertIsInstance(backend, ClaudeCLIBackend)
        self.assertEqual(backend.name, "GLM")
        self.assertEqual(backend._cli_path, "/bin/claude-zai")
        self.assertEqual(backend._max_turns, 15)
        self.assertEqual(backend._timeout, 600)

    def test_rejects_unknown_name(self):
        with self.assertRaises(KeyError):
            registry.get_backend("Inconnu")


if __name__ == "__main__":
    unittest.main()
