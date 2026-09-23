from __future__ import annotations

from leadcompass.config import BusinessProfile
from leadcompass.llm.base import LLMBackend
from leadcompass.tasks.prompts import drafting_system_prompt


def generate_draft(
    contact_context: str,
    profile: BusinessProfile,
    draft_type: str,
    backend: LLMBackend,
    extra_instructions: str = "",
) -> str:
    system = drafting_system_prompt(profile, draft_type)
    user_message = contact_context
    if extra_instructions.strip():
        user_message += f"\n\nConsignes spécifiques pour cet email :\n{extra_instructions.strip()}"
    return backend.generate(system, user_message)


def compare_drafts(
    contact_context: str,
    profile: BusinessProfile,
    draft_type: str,
    backends: list[LLMBackend],
    extra_instructions: str = "",
) -> dict[str, str]:
    return {
        backend.name: generate_draft(contact_context, profile, draft_type, backend, extra_instructions)
        for backend in backends
    }
