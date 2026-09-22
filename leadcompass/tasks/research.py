from __future__ import annotations

from leadcompass.config import BusinessProfile
from leadcompass.llm.base import LLMBackend
from leadcompass.tasks.prompts import research_system_prompt


def generate_summary(contact_context: str, profile: BusinessProfile, backend: LLMBackend) -> str:
    system = research_system_prompt(profile)
    return backend.generate(system, contact_context)
