from __future__ import annotations

import streamlit as st

from leadcompass.config import load_business_profile
from leadcompass.hubspot_client import HubSpotClient, HubSpotError
from leadcompass.llm.claude_cli import ClaudeCLIBackend
from leadcompass.llm.glm import GLMBackend
from leadcompass.tasks.drafting import compare_drafts, generate_draft
from leadcompass.tasks.prompts import DRAFT_TYPES
from leadcompass.tasks.research import generate_summary
from leadcompass.tasks.scoring import generate_score

st.set_page_config(page_title="LeadCompass", page_icon="🧭")
st.title("🧭 LeadCompass")

profile = load_business_profile()
if not profile.is_configured:
    st.warning(
        "Le profil entreprise n'est pas configuré. "
        "Rends-toi sur la page Paramètres pour le renseigner."
    )

claude = ClaudeCLIBackend()

try:
    hubspot = HubSpotClient()
except HubSpotError as exc:
    st.error(f"Configuration HubSpot manquante : {exc}")
    st.stop()


def _contact_context(contact: dict, engagements: list[dict]) -> str:
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
        body = eprops.get("hs_note_body") or eprops.get("hs_email_text", "")
        lines.append(f"- [{engagement.get('engagement_type')}] {body[:300]}")
    return "\n".join(lines)


query = st.text_input("Rechercher un prospect (nom, email, entreprise)")
contact = None
if query:
    results = hubspot.search_contacts(query)
    if not results:
        st.info("Aucun prospect trouvé.")
    else:
        options = {
            f"{r['properties'].get('firstname', '')} {r['properties'].get('lastname', '')} "
            f"— {r['properties'].get('email', '')}": r
            for r in results
        }
        choice = st.selectbox("Prospect", list(options.keys()))
        contact = options[choice]

if not contact:
    st.stop()

contact_id = contact["id"]
engagements = hubspot.get_engagements(contact_id)
context = _contact_context(contact, engagements)

tab_summary, tab_score, tab_draft = st.tabs(["Résumé", "Score", "Rédaction"])

with tab_summary:
    summary_key = f"summary_{contact_id}"
    if st.button("Générer le résumé"):
        with st.spinner("Génération en cours..."):
            st.session_state[summary_key] = generate_summary(context, profile, claude)

    if summary_key in st.session_state:
        st.write(st.session_state[summary_key])
        if st.button("Enregistrer dans HubSpot (note)", key=f"save_summary_{contact_id}"):
            hubspot.create_note(contact_id, st.session_state[summary_key])
            st.success("Résumé enregistré dans HubSpot.")

with tab_score:
    score_key = f"score_{contact_id}"
    if st.button("Calculer le score"):
        with st.spinner("Évaluation en cours..."):
            st.session_state[score_key] = generate_score(context, profile, claude)

    if score_key in st.session_state:
        result = st.session_state[score_key]
        st.metric("Score", f"{result.percentage} %", result.classification.capitalize())
        for detail in result.details:
            st.write(f"- {detail.get('name')} : {detail.get('score')}/5 — {detail.get('justification')}")
        if st.button("Enregistrer le score dans HubSpot", key=f"save_score_{contact_id}"):
            hubspot.ensure_custom_properties()
            hubspot.update_score(contact_id, result.total, result.classification)
            st.success("Score enregistré dans HubSpot.")

with tab_draft:
    draft_type = st.selectbox(
        "Type d'email", list(DRAFT_TYPES.keys()), format_func=lambda k: DRAFT_TYPES[k]
    )
    compare = st.checkbox("Comparer avec GLM")
    drafts_key = f"drafts_{contact_id}_{draft_type}_{compare}"

    if st.button("Générer"):
        with st.spinner("Rédaction en cours..."):
            if compare:
                st.session_state[drafts_key] = compare_drafts(
                    context, profile, draft_type, [claude, GLMBackend()]
                )
            else:
                st.session_state[drafts_key] = {
                    claude.name: generate_draft(context, profile, draft_type, claude)
                }

    if drafts_key in st.session_state:
        drafts = st.session_state[drafts_key]
        columns = st.columns(len(drafts))
        for col, (backend_name, text) in zip(columns, drafts.items()):
            with col:
                st.subheader(backend_name)
                area_key = f"draft_text_{contact_id}_{draft_type}_{backend_name}"
                st.text_area("", text, height=300, key=area_key)
                if st.button("Enregistrer cette version", key=f"save_draft_{area_key}"):
                    hubspot.create_note(contact_id, st.session_state[area_key])
                    st.success("Email enregistré dans HubSpot.")
