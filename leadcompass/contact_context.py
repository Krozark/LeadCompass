from __future__ import annotations


def _engagement_label(engagement: dict) -> str:
    if engagement.get("engagement_type") != "emails":
        return engagement.get("engagement_type", "")
    # HubSpot : hs_email_direction = EMAIL (envoyé) / INCOMING_EMAIL (reçu)
    direction = engagement.get("properties", {}).get("hs_email_direction", "")
    if "INCOMING" in direction:
        return "email reçu"
    if direction:
        return "email envoyé"
    return "emails"


def build_contact_context(contact: dict, engagements: list[dict]) -> str:
    props = contact.get("properties", {})
    lines = [
        f"Nom : {props.get('firstname', '')} {props.get('lastname', '')}",
        f"Email : {props.get('email', '')}",
        f"Entreprise : {props.get('company', '')}",
        f"Poste : {props.get('jobtitle', '')}",
        "",
        "Historique des échanges :",
    ]
    for engagement in engagements:
        eprops = engagement.get("properties", {})
        body = eprops.get("hs_note_body") or eprops.get("hs_email_text") or ""
        lines.append(f"- [{_engagement_label(engagement)}] {body[:300]}")
    return "\n".join(lines)
