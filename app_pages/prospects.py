from __future__ import annotations

import contextlib
from datetime import datetime

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

st.title("Prospects")

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
def _list_contacts_page(after: str | None) -> tuple[list[dict], str | None]:
    return _get_hubspot_client().list_contacts(after=after)


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


# ── Session state defaults ────────────────────────────────────────────────────
st.session_state.setdefault("search_query", "")
st.session_state.setdefault("search_results", [])
st.session_state.setdefault("search_after", None)

# ── Layout: prospect list (left) + detail panel (right) ──────────────────────
col_list, col_detail = st.columns([1, 2])

with col_list:
    with st.form("search_form", border=False), st.container(horizontal=True, vertical_alignment="bottom"):
        query_input = st.text_input(
            "Rechercher",
            value=st.session_state["search_query"],
            type="search",
            placeholder="Nom, email, entreprise…",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Rechercher", icon=":material/search:")

    if submitted:
        st.session_state["search_query"] = query_input
        st.session_state["search_results"] = []
        st.session_state["search_after"] = None

    # Load first page when results list is empty
    if not st.session_state["search_results"]:
        active_query = st.session_state["search_query"]
        if active_query:
            results, after = _search_contacts_page(active_query, None)
        else:
            results, after = _list_contacts_page(None)
        st.session_state["search_results"] = results
        st.session_state["search_after"] = after

    results: list[dict] = st.session_state["search_results"]

    if not results:
        st.info("Aucun prospect trouvé.")
        st.stop()

    def _label(i: int) -> str:
        props = results[i]["properties"]
        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or "—"
        company = props.get("company") or ""
        return f"{name}  —  {company}" if company else name

    choice_idx = st.radio(
        "Sélectionner un prospect",
        range(len(results)),
        format_func=_label,
        label_visibility="collapsed",
    )

    if st.session_state["search_after"] and st.button("Voir plus", icon=":material/expand_more:"):
        active_query = st.session_state["search_query"]
        if active_query:
            more, after = _search_contacts_page(active_query, st.session_state["search_after"])
        else:
            more, after = _list_contacts_page(st.session_state["search_after"])
        st.session_state["search_results"] = results + more
        st.session_state["search_after"] = after
        st.rerun()

contact = results[choice_idx]

# ── Detail panel ──────────────────────────────────────────────────────────────
with col_detail:
    props = contact["properties"]
    name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or "—"
    st.subheader(name)

    with st.container(border=True):
        info_cols = st.columns(3)
        info_cols[0].markdown(f"**Email**  \n{props.get('email') or '—'}")
        info_cols[1].markdown(f"**Entreprise**  \n{props.get('company') or '—'}")
        info_cols[2].markdown(f"**Poste**  \n{props.get('jobtitle') or '—'}")

    contact_id = contact["id"]
    engagements = _get_engagements(contact_id)
    context = build_contact_context(contact, engagements)

    tab_summary, tab_score, tab_draft, tab_exchanges = st.tabs(["Résumé", "Score", "Rédaction", "Échanges"])

    with tab_summary:
        summary_key = f"summary_{contact_id}"
        if st.button("Générer le résumé", icon=":material/auto_awesome:"):
            with st.spinner("Génération en cours..."):
                st.session_state[summary_key] = generate_summary(context, profile, claude)

        if summary_key in st.session_state:
            st.write(st.session_state[summary_key])
            if st.button(
                "Enregistrer dans HubSpot", key=f"save_summary_{contact_id}", icon=":material/save:"
            ):
                _save_note(contact_id, st.session_state[summary_key])

    with tab_score:
        score_key = f"score_{contact_id}"
        if st.button("Calculer le score", icon=":material/star:"):
            with st.spinner("Évaluation en cours..."):
                st.session_state[score_key] = generate_score(context, profile, claude)

        if score_key in st.session_state:
            result = st.session_state[score_key]
            st.metric("Score", f"{result.percentage} %", result.classification.capitalize())
            for detail in result.details:
                st.write(f"- {detail.get('name')} : {detail.get('score')}/5 — {detail.get('justification')}")
            if st.button(
                "Enregistrer le score dans HubSpot",
                key=f"save_score_{contact_id}",
                icon=":material/save:",
            ):
                try:
                    hubspot.ensure_custom_properties()
                    hubspot.update_score(contact_id, result.total, result.classification)
                    st.success("Score enregistré dans HubSpot.")
                except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                    st.error(f"Échec de l'enregistrement du score : {exc}")

    with tab_draft:
        draft_type = st.selectbox(
            "Type d'email", list(DRAFT_TYPES.keys()), format_func=lambda k: DRAFT_TYPES[k]
        )
        compare = st.toggle("Comparer avec GLM")
        drafts_key = f"drafts_{contact_id}_{draft_type}_{compare}"

        if st.button("Générer", icon=":material/edit:"):
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
                    st.text_area("Brouillon", text, height=300, key=area_key, label_visibility="collapsed")
                    if st.button(
                        "Enregistrer cette version",
                        key=f"save_draft_{area_key}",
                        icon=":material/save:",
                    ):
                        _save_note(contact_id, st.session_state[area_key])

    with tab_exchanges:
        _EXCHANGE_TYPES = {"note": "Note", "sent": "Email envoyé", "received": "Email reçu"}
        exchange_type = st.segmented_control(
            "Type d'échange",
            options=list(_EXCHANGE_TYPES.keys()),
            format_func=lambda k: _EXCHANGE_TYPES[k],
            default="note",
            key=f"exchange_type_{contact_id}",
        )

        with st.form(f"new_exchange_form_{contact_id}", border=False):
            if exchange_type in ("sent", "received"):
                subject_input = st.text_input("Sujet", placeholder="Sujet de l'email")
            else:
                subject_input = ""
            note_text = st.text_area(
                "Contenu",
                placeholder="Résumé d'un appel, note de contexte, corps de l'email…",
                height=100,
                label_visibility="collapsed",
            )
            add_submitted = st.form_submit_button("Ajouter", icon=":material/add:")

        if add_submitted:
            if note_text.strip():
                try:
                    if exchange_type == "note":
                        hubspot.create_note(contact_id, note_text.strip())
                    else:
                        direction = "INCOMING_EMAIL" if exchange_type == "received" else "EMAIL"
                        hubspot.create_email_log(
                            contact_id, note_text.strip(), direction, subject_input.strip()
                        )
                    _get_engagements.clear()
                    st.success("Échange enregistré.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                    st.error(f"Échec de l'enregistrement : {exc}")
            else:
                st.warning("Le contenu ne peut pas être vide.")

        st.divider()

        if not engagements:
            st.caption("Aucun échange enregistré pour ce prospect.")
        else:
            recent = list(reversed(engagements))
            for idx, eng in enumerate(recent):
                eprops = eng.get("properties", {})
                eng_type = eng.get("engagement_type", "notes")
                is_email = eng_type == "emails"

                ts = eprops.get("hs_timestamp")
                date_str = ""
                if ts:
                    with contextlib.suppress(ValueError, OSError):
                        date_str = datetime.fromtimestamp(int(ts) / 1000).strftime("%d/%m/%Y %H:%M")

                body = eprops.get("hs_note_body") or eprops.get("hs_email_text") or ""

                if is_email:
                    subject = eprops.get("hs_email_subject") or "Email"
                    direction = eprops.get("hs_email_direction", "")
                    dir_label = "reçu" if "INCOMING" in direction else "envoyé"
                    label = f"{subject}  ·  {dir_label}" + (f"  ·  {date_str}" if date_str else "")
                    icon = ":material/mail:"
                else:
                    preview = (body[:60] + "…") if len(body) > 60 else body
                    label = ("Note" + (f"  ·  {date_str}" if date_str else "")) + (
                        f"  —  {preview}" if preview else ""
                    )
                    icon = ":material/note:"

                with st.expander(label, icon=icon, expanded=(idx < 3)):
                    if body:
                        st.markdown(body)
                    else:
                        st.caption("Aucun contenu.")
