from __future__ import annotations

from leadcompass.config import BusinessProfile
from leadcompass.llm.base import LLMBackend
from leadcompass.tasks.prompts import research_system_prompt


def generate_summary(
    contact_context: str,
    profile: BusinessProfile,
    backend: LLMBackend,
    extra_context: str = "",
) -> str:
    system = research_system_prompt(profile)
    user_message = contact_context
    if extra_context.strip():
        user_message += (
            f"\n\nInformations complémentaires fournies par le commercial :\n{extra_context.strip()}"
        )
    return backend.generate(system, user_message)
