from __future__ import annotations

from leadcompass.config import BusinessProfile

DRAFT_TYPES = {
    "premier_contact": "un premier email de prise de contact",
    "relance": "un email de relance suite à un échange resté sans réponse",
    "reponse": "une réponse au dernier message reçu du prospect",
}


def research_system_prompt(profile: BusinessProfile) -> str:
    return (
        "Tu es un assistant commercial. Tu aides à qualifier des prospects pour "
        f"l'entreprise suivante :\n{profile.to_prompt_context()}\n\n"
        "Utilise les informations fournies sur le prospect, complète-les si besoin "
        "par une recherche web sur l'entreprise ou la personne, puis rédige un "
        "résumé synthétique en français, factuel, sans invention."
    )


def scoring_system_prompt(profile: BusinessProfile) -> str:
    criteria_text = "\n".join(
        f"- {c.name} (poids {c.weight}) : {c.description}" for c in profile.scoring_criteria
    )
    return (
        "Tu es un assistant commercial. Tu notes la pertinence d'un prospect pour "
        f"l'entreprise suivante :\n{profile.to_prompt_context()}\n\n"
        f"Grille de critères, note chacun de 0 à 5 :\n{criteria_text}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON de la forme "
        '{"criteria_scores": [{"name": "...", "score": 0, "justification": "..."}]}, '
        "sans texte autour, sans bloc markdown."
    )


def drafting_system_prompt(profile: BusinessProfile, draft_type: str) -> str:
    objectif = DRAFT_TYPES.get(draft_type, draft_type)
    return (
        "Tu es un assistant commercial. Tu rédiges des emails pour l'entreprise "
        f"suivante :\n{profile.to_prompt_context()}\n\n"
        f"Rédige {objectif}, en français, dans le ton défini ci-dessus. "
        "Ne mets pas d'objet, uniquement le corps du mail."
    )
