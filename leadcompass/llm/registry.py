from __future__ import annotations

import functools
import shutil
from collections.abc import Callable

from leadcompass.config import CLAUDE_CLI_PATH, ZAI_API_KEY, load_llm_choice
from leadcompass.llm.base import LLMBackend
from leadcompass.llm.claude_cli import ClaudeCLIBackend
from leadcompass.llm.glm import GLMBackend


def claude_cli_available() -> bool:
    return shutil.which(CLAUDE_CLI_PATH) is not None


def configured_backends() -> dict[str, Callable[[], LLMBackend]]:
    """Factories of every backend whose prerequisite (CLI binary, API key) is present."""
    backends: dict[str, Callable[[], LLMBackend]] = {}
    if claude_cli_available():
        backends[ClaudeCLIBackend.name] = ClaudeCLIBackend
    if ZAI_API_KEY:
        backends[GLMBackend.name] = GLMBackend
    return backends


def default_backend_name() -> str:
    """Saved choice when still available, else the first configured backend."""
    backends = configured_backends()
    saved = load_llm_choice()
    if saved in backends:
        return saved
    return next(iter(backends), "")


@functools.cache
def get_backend(name: str) -> LLMBackend:
    factory = configured_backends().get(name)
    if factory is None:
        raise KeyError(f"LLM backend not configured: {name}")
    return factory()
