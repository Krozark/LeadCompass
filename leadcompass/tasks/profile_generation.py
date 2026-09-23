from __future__ import annotations

import json
import re

from leadcompass.config import BusinessProfile
from leadcompass.llm.claude_cli import ClaudeCLIBackend, ClaudeCLIError

_SYSTEM_PROMPT = (
    "Tu es un assistant qui configure un outil d'aide à la prospection commerciale "
    "pour une entreprise. Explore les dossiers fournis avec tes outils de lecture "
    "de fichiers pour comprendre l'activité de l'entreprise : son produit ou "
    "service, sa clientèle cible, ce qui la différencie, et sur quels critères "
    "elle devrait juger la pertinence d'un prospect commercial. Ignore les "
    "fichiers binaires non pertinents (images, vidéos, archives).\n\n"
    "Réponds UNIQUEMENT avec un objet JSON de la forme :\n"
    '{"name": "...", "product_description": "...", "target_customer": "...", '
    '"value_proposition": "...", "tone": "...", '
    '"scoring_criteria": [{"name": "...", "description": "...", "weight": 1}]}\n'
    "sans texte autour, sans bloc markdown."
)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ClaudeCLIError(f"Aucun JSON trouvé dans la réponse du modèle : {text[:300]}")
    return json.loads(match.group(0))


def generate_profile_from_folders(
    folders: list[tuple[str, str]],
    existing_profile: BusinessProfile,
    backend: ClaudeCLIBackend,
) -> BusinessProfile:
    """Explore `folders` and return a (re)generated business profile.

    Each folder is a ``(path, description)`` tuple; description may be empty.
    Only makes sense with a backend that can actually browse the filesystem
    (Claude via the CLI) — GLM has no file access and would just hallucinate.
    """
    directories = [path for path, _ in folders]

    folder_lines = []
    for path, description in folders:
        line = f"- {path}"
        if description.strip():
            line += f" — {description.strip()}"
        folder_lines.append(line)

    user_prompt = "Dossiers à explorer :\n" + "\n".join(folder_lines)
    if existing_profile.is_configured:
        user_prompt += (
            "\n\nProfil actuel à affiner/mettre à jour à la lumière de ces dossiers "
            "(ne pars pas de zéro si rien ne le contredit) :\n"
            + json.dumps(existing_profile.to_dict(), ensure_ascii=False)
        )

    raw = backend.explore(_SYSTEM_PROMPT, user_prompt, directories)
    return BusinessProfile.from_dict(_extract_json(raw))
