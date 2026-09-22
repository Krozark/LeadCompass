from __future__ import annotations

import streamlit as st

from leadcompass.config import load_business_profile
from leadcompass.contact_context import build_contact_context
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
        "Le profil entreprise n'est pas configuré. Rends-toi sur la page Paramètres pour le renseigner."
    )

claude = ClaudeCLIBackend()


@st.cache_resource
def _get_hubspot_client() -> HubSpotClient:
    return HubSpotClient()


@st.cache_data(ttl=300)
def _search_contacts_page(query: str, after: str | None) -> tuple[list[dict], str | None]:
    return _get_hubspot_client().search_contacts(query, after=after)


@st.cache_data(ttl=300)
def _get_engagements(contact_id: str) -> list[dict]:
    return _get_hubspot_client().get_engagements(contact_id)


try:
    hubspot = _get_hubspot_client()
except HubSpotError as exc:
    st.error(f"Configuration HubSpot manquante : {exc}")
    st.stop()


def _save_note(contact_id: str, text: str) -> None:
    try:
        hubspot.create_note(contact_id, text)
        st.success("Enregistré dans HubSpot.")
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        st.error(f"Échec de l'enregistrement dans HubSpot : {exc}")


query = st.text_input("Rechercher un prospect (nom, email, entreprise)")
contact = None
if query:
    if st.session_state.get("search_query") != query:
        results, after = _search_contacts_page(query, None)
        st.session_state["search_query"] = query
        st.session_state["search_results"] = results
        st.session_state["search_after"] = after

    results = st.session_state["search_results"]
    if not results:
        st.info("Aucun prospect trouvé.")
    else:

        def _label(i: int) -> str:
            props = results[i]["properties"]
            return f"{props.get('firstname', '')} {props.get('lastname', '')} — {props.get('email', '')}"

        choice_idx = st.selectbox("Prospect", range(len(results)), format_func=_label)
        contact = results[choice_idx]

        if st.session_state["search_after"] and st.button("Voir plus de résultats"):
            more, after = _search_contacts_page(query, st.session_state["search_after"])
            st.session_state["search_results"] = results + more
            st.session_state["search_after"] = after
            st.rerun()

if not contact:
    st.stop()

contact_id = contact["id"]
engagements = _get_engagements(contact_id)
context = build_contact_context(contact, engagements)

tab_summary, tab_score, tab_draft = st.tabs(["Résumé", "Score", "Rédaction"])

with tab_summary:
    summary_key = f"summary_{contact_id}"
    if st.button("Générer le résumé"):
        with st.spinner("Génération en cours..."):
            st.session_state[summary_key] = generate_summary(context, profile, claude)

    if summary_key in st.session_state:
        st.write(st.session_state[summary_key])
        if st.button("Enregistrer dans HubSpot (note)", key=f"save_summary_{contact_id}"):
            _save_note(contact_id, st.session_state[summary_key])

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
            try:
                hubspot.ensure_custom_properties()
                hubspot.update_score(contact_id, result.total, result.classification)
                st.success("Score enregistré dans HubSpot.")
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                st.error(f"Échec de l'enregistrement du score : {exc}")

with tab_draft:
    draft_type = st.selectbox("Type d'email", list(DRAFT_TYPES.keys()), format_func=lambda k: DRAFT_TYPES[k])
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
        for col, (backend_name, text) in zip(columns, drafts.items(), strict=True):
            with col:
                st.subheader(backend_name)
                area_key = f"draft_text_{contact_id}_{draft_type}_{backend_name}"
                st.text_area("", text, height=300, key=area_key)
                if st.button("Enregistrer cette version", key=f"save_draft_{area_key}"):
                    _save_note(contact_id, st.session_state[area_key])
