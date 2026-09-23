from __future__ import annotations

import contextlib
from datetime import date, datetime
from datetime import time as dtime

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


# Notes created by LeadCompass (summaries, scores, drafts) carry this prefix so
# they are never confused with manual exchange logs in the Échanges tab.
_LC_PREFIX = "[LeadCompass] "

_EXCHANGE_DIR = {"sent": "EMAIL", "received": "INCOMING_EMAIL"}
_EXCHANGE_LABELS = {"sent": "Email envoyé", "received": "Email reçu"}


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return ""
    with contextlib.suppress(ValueError, OSError):
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%d/%m/%Y %H:%M")
    return ""


def _save_note(contact_id: str, text: str) -> None:
    try:
        hubspot.create_note(contact_id, _LC_PREFIX + text)
        st.success("Enregistré dans HubSpot.")
    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
        st.error(f"Échec de l'enregistrement dans HubSpot : {exc}")


def _ts_to_dt(ts: str | None) -> datetime:
    if ts:
        with contextlib.suppress(ValueError, OSError):
            return datetime.fromtimestamp(int(ts) / 1000)
    return datetime.now()


@st.dialog("Modifier l'échange")
def _edit_exchange_dialog(eng: dict, eng_type: str) -> None:
    eprops = eng.get("properties", {})
    eng_id = eng.get("id", "")

    current_dir = eprops.get("hs_email_direction", "")
    default_type = "received" if "INCOMING" in current_dir else "sent"
    new_type = st.segmented_control(
        "Type",
        options=["sent", "received"],
        format_func=lambda k: _EXCHANGE_LABELS[k],
        default=default_type,
    )
    new_subject = st.text_input("Sujet", value=eprops.get("hs_email_subject") or "")

    current_dt = _ts_to_dt(eprops.get("hs_timestamp"))
    col_d, col_t = st.columns(2)
    new_date = col_d.date_input("Date", value=current_dt.date())
    new_time = col_t.time_input("Heure", value=current_dt.time().replace(second=0, microsecond=0), step=300)

    new_body = st.text_area(
        "Contenu", value=eprops.get("hs_email_text") or "", height=200, label_visibility="collapsed"
    )

    if st.button("Enregistrer", icon=":material/save:", type="primary"):
        try:
            ts_ms = int(datetime.combine(new_date, new_time).timestamp() * 1000)
            hubspot.update_email_log(eng_id, new_body, _EXCHANGE_DIR[new_type], new_subject, ts_ms)
            _get_engagements.clear()
            st.rerun()
        except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
            st.error(f"Échec de la modification : {exc}")


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
        exchange_type = st.segmented_control(
            "Type",
            options=list(_EXCHANGE_LABELS.keys()),
            format_func=lambda k: _EXCHANGE_LABELS[k],
            default="sent",
            key=f"exchange_type_{contact_id}",
        )

        with st.form(f"new_exchange_form_{contact_id}", border=False):
            subject_input = st.text_input("Sujet", placeholder="Sujet de l'email")
            col_d, col_t = st.columns(2)
            add_date = col_d.date_input("Date", value=date.today())
            add_time = col_t.time_input(
                "Heure", value=dtime(datetime.now().hour, datetime.now().minute), step=300
            )
            note_text = st.text_area(
                "Contenu",
                placeholder="Corps de l'email…",
                height=100,
                label_visibility="collapsed",
            )
            add_submitted = st.form_submit_button("Ajouter", icon=":material/add:")

        if add_submitted:
            if note_text.strip():
                try:
                    ts_ms = int(datetime.combine(add_date, add_time).timestamp() * 1000)
                    hubspot.create_email_log(
                        contact_id,
                        note_text.strip(),
                        _EXCHANGE_DIR[exchange_type],
                        subject_input.strip(),
                        ts_ms,
                    )
                    _get_engagements.clear()
                    st.success("Échange enregistré.")
                    st.rerun()
                except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                    st.error(f"Échec de l'enregistrement : {exc}")
            else:
                st.warning("Le contenu ne peut pas être vide.")

        st.divider()

        # Échanges = emails only (notes are used internally for prospect info)
        exchanges = [e for e in engagements if e.get("engagement_type") == "emails"]

        if not exchanges:
            st.caption("Aucun échange enregistré pour ce prospect.")
        else:
            for idx, eng in enumerate(reversed(exchanges)):
                eprops = eng.get("properties", {})
                eng_type = eng.get("engagement_type", "notes")
                is_email = eng_type == "emails"
                eng_id = eng.get("id", "")

                date_str = _fmt_ts(eprops.get("hs_timestamp"))
                body = eprops.get("hs_note_body") or eprops.get("hs_email_text") or ""

                if is_email:
                    subject = eprops.get("hs_email_subject") or "Email"
                    raw_dir = eprops.get("hs_email_direction", "")
                    dir_label = "reçu" if "INCOMING" in raw_dir else "envoyé"
                    label = f"{subject}  ·  {dir_label}" + (f"  ·  {date_str}" if date_str else "")
                    exp_icon = ":material/mail:"
                else:
                    preview = (body[:60] + "…") if len(body) > 60 else body
                    label = ("Note" + (f"  ·  {date_str}" if date_str else "")) + (
                        f"  —  {preview}" if preview else ""
                    )
                    exp_icon = ":material/note:"

                with st.expander(label, icon=exp_icon, expanded=(idx < 3)):
                    if date_str:
                        st.caption(date_str)
                    if body:
                        st.markdown(body)
                    else:
                        st.caption("Aucun contenu.")
                    if st.button("Modifier", key=f"edit_{eng_id}", icon=":material/edit:"):
                        _edit_exchange_dialog(eng, eng_type)
