from __future__ import annotations

import json
import re

from leadcompass.config import BusinessProfile
from leadcompass.llm.base import LLMBackend
from leadcompass.tasks.prompts import discovery_system_prompt

_RESULT_FIELDS = ("name", "organization", "role", "email", "website", "why_relevant")


def _extract_json_array(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        raise ValueError(f"Aucun tableau JSON trouvé dans la réponse du modèle : {text[:300]}")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide dans la réponse du modèle : {text[:300]}") from exc
    if not isinstance(data, list):
        raise ValueError(f"La réponse du modèle n'est pas un tableau : {text[:300]}")
    return [
        {field: str(item.get(field, "") or "") for field in _RESULT_FIELDS}
        for item in data
        if isinstance(item, dict)
    ]


def discover_prospects(
    guide: str,
    profile: BusinessProfile,
    backend: LLMBackend,
    count: int = 10,
) -> list[dict]:
    """Recherche de nouveaux contacts (prospects, influenceurs...) sur le web.

    `guide` est une description libre de ce que le commercial cherche ; nécessite
    un backend avec accès web (Claude via le CLI).
    """
    system = discovery_system_prompt(profile)
    user = f"Recherche : {guide.strip()}\n\nPropose jusqu'à {count} contacts."
    return _extract_json_array(backend.generate(system, user))
