from __future__ import annotations

from leadcompass.config import BusinessProfile
from leadcompass.llm.base import LLMBackend
from leadcompass.tasks.prompts import drafting_system_prompt


def generate_draft(
    contact_context: str, profile: BusinessProfile, draft_type: str, backend: LLMBackend
) -> str:
    system = drafting_system_prompt(profile, draft_type)
    return backend.generate(system, contact_context)


def compare_drafts(
    contact_context: str,
    profile: BusinessProfile,
    draft_type: str,
    backends: list[LLMBackend],
) -> dict[str, str]:
    return {
        backend.name: generate_draft(contact_context, profile, draft_type, backend)
        for backend in backends
    }
