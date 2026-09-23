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
    known_identities: list[str] | None = None,
) -> list[dict]:
    """Recherche de nouveaux contacts (prospects, influenceurs...) sur le web.

    `guide` est une description libre de ce que le commercial cherche ; nécessite
    un backend avec accès web (Claude via le CLI). `known_identities` liste les
    noms/organisations déjà dans HubSpot, que le modèle doit exclure.
    """
    system = discovery_system_prompt(profile)
    user = f"Recherche : {guide.strip()}\n\nPropose jusqu'à {count} contacts."
    if known_identities:
        listed = "\n".join(f"- {identity}" for identity in known_identities)
        user += "\n\nExclus strictement ces contacts et organisations, déjà connus :\n" + listed
    return _extract_json_array(backend.generate(system, user))


def _norm(value: str) -> str:
    return " ".join(value.lower().split())


def split_known_leads(
    results: list[dict],
    known_emails: set[str],
    known_identities: set[str],
) -> tuple[list[dict], int]:
    """Sépare les résultats déjà connus de HubSpot des nouveaux contacts.

    Un résultat est masqué si son email, son nom complet ou son organisation
    (comparaison insensible à la casse et aux espaces superflus) correspond à un
    contact existant. Retourne (nouveaux résultats, nombre de masqués).
    """
    kept: list[dict] = []
    hidden = 0
    emails = {_norm(value) for value in known_emails}
    identities = {_norm(value) for value in known_identities}
    for lead in results:
        email = _norm(lead.get("email", ""))
        name = _norm(lead.get("name", ""))
        org = _norm(lead.get("organization", ""))
        if (email and email in emails) or (name and name in identities) or (org and org in identities):
            hidden += 1
        else:
            kept.append(lead)
    return kept, hidden
