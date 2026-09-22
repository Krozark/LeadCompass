from __future__ import annotations


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
        lines.append(f"- [{engagement.get('engagement_type')}] {body[:300]}")
    return "\n".join(lines)
