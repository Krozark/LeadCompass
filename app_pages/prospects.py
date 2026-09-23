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
def _filter_contacts_page(type_value: str, after: str | None) -> tuple[list[dict], str | None]:
    return _get_hubspot_client().filter_contacts_by_type(type_value, after=after)


@st.cache_data(ttl=300)
def _get_engagements(contact_id: str) -> list[dict]:
    return _get_hubspot_client().get_engagements(contact_id)


try:
    hubspot = _get_hubspot_client()
except HubSpotError as exc:
    st.error(f"Configuration HubSpot manquante : {exc}")
    st.stop()


# Notes created by LeadCompass carry a typed prefix so different note kinds can
# be retrieved and displayed in the right tab.
_LC_PREFIX = "[LeadCompass] "  # legacy / generic fallback
_LC_SUMMARY_PREFIX = "[LeadCompass:résumé] "
_LC_DRAFT_PREFIX = "[LeadCompass:brouillon] "

_EXCHANGE_DIR = {"sent": "EMAIL", "received": "INCOMING_EMAIL"}
_EXCHANGE_LABELS = {"sent": "Email envoyé", "received": "Email reçu"}


def _fmt_ts(ts: str | None) -> str:
    if not ts:
        return ""
    with contextlib.suppress(ValueError, OSError):
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%d/%m/%Y %H:%M")
    return ""


def _save_note(contact_id: str, text: str, prefix: str = _LC_PREFIX) -> None:
    try:
        hubspot.create_note(contact_id, prefix + text)
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
st.session_state.setdefault("type_filter", "")

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

    if profile.prospect_types:
        type_options = ["Tous les types", *profile.prospect_types]
        current_filter = st.session_state["type_filter"]
        selected_label = st.selectbox(
            "Filtrer par type",
            type_options,
            index=type_options.index(current_filter) if current_filter in type_options else 0,
            label_visibility="collapsed",
        )
        new_filter = "" if selected_label == "Tous les types" else selected_label
        if new_filter != st.session_state["type_filter"]:
            st.session_state["type_filter"] = new_filter
            st.session_state["search_results"] = []
            st.session_state["search_after"] = None
            st.rerun()

    # Load first page when results list is empty
    if not st.session_state["search_results"]:
        active_query = st.session_state["search_query"]
        active_type = st.session_state["type_filter"]
        if active_query:
            results, after = _search_contacts_page(active_query, None)
        elif active_type:
            results, after = _filter_contacts_page(active_type, None)
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
        active_type = st.session_state["type_filter"]
        cursor = st.session_state["search_after"]
        if active_query:
            more, after = _search_contacts_page(active_query, cursor)
        elif active_type:
            more, after = _filter_contacts_page(active_type, cursor)
        else:
            more, after = _list_contacts_page(cursor)
        st.session_state["search_results"] = results + more
        st.session_state["search_after"] = after
        st.rerun()

contact = results[choice_idx]

# ── Detail panel ──────────────────────────────────────────────────────────────
with col_detail:
    props = contact["properties"]
    contact_id = contact["id"]
    name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or "—"
    st.subheader(name)

    with st.container(border=True):
        info_cols = st.columns(3)
        info_cols[0].markdown(f"**Email**  \n{props.get('email') or '—'}")
        info_cols[1].markdown(f"**Entreprise**  \n{props.get('company') or '—'}")
        info_cols[2].markdown(f"**Poste**  \n{props.get('jobtitle') or '—'}")

    if profile.prospect_types:
        type_key = f"prospect_type_select_{contact_id}"
        current_type = props.get("leadcompass__type_de_prospect") or ""
        type_options = ["", *profile.prospect_types]

        def _on_type_change(cid: str = contact_id) -> None:
            new_val = st.session_state[type_key]
            try:
                hubspot.set_prospect_type(cid, new_val)
                _list_contacts_page.clear()
                _search_contacts_page.clear()
                _filter_contacts_page.clear()
            except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                st.error(f"Échec de l'enregistrement du type : {exc}")

        st.selectbox(
            "Type de prospect",
            type_options,
            index=type_options.index(current_type) if current_type in type_options else 0,
            key=type_key,
            on_change=_on_type_change,
            format_func=lambda v: v or "— Choisir un type —",
        )

    engagements = _get_engagements(contact_id)
    context = build_contact_context(contact, engagements)

    tab_summary, tab_score, tab_draft, tab_exchanges = st.tabs(["Résumé", "Score", "Rédaction", "Échanges"])

    with tab_summary:
        summary_key = f"summary_{contact_id}"

        # Pre-load from the most recent résumé note saved in HubSpot
        if summary_key not in st.session_state:
            for eng in reversed(engagements):
                if eng.get("engagement_type") != "notes":
                    continue
                body = eng.get("properties", {}).get("hs_note_body") or ""
                if body.startswith(_LC_SUMMARY_PREFIX):
                    st.session_state[summary_key] = body[len(_LC_SUMMARY_PREFIX) :]
                    break
                if body.startswith(_LC_PREFIX):  # backward compat with old notes
                    st.session_state[summary_key] = body[len(_LC_PREFIX) :]
                    break

        extra_info = st.text_area(
            "Informations complémentaires",
            placeholder="Contexte supplémentaire à transmettre à l'IA (ex. : secteur d'activité, besoin identifié, remarques…)",
            height=80,
            key=f"summary_extra_{contact_id}",
        )

        if st.button("Générer le résumé", icon=":material/auto_awesome:"):
            with st.spinner("Génération en cours..."):
                st.session_state[summary_key] = generate_summary(context, profile, claude, extra_info)

        if summary_key in st.session_state:
            st.write(st.session_state[summary_key])
            if st.button(
                "Enregistrer dans HubSpot", key=f"save_summary_{contact_id}", icon=":material/save:"
            ):
                _save_note(contact_id, st.session_state[summary_key], prefix=_LC_SUMMARY_PREFIX)

    with tab_score:
        score_key = f"score_{contact_id}"

        # Show score stored in HubSpot when no fresh result is in session
        stored_score = props.get("leadcompass__score_de_pertinence")
        stored_classif = props.get("leadcompas__classification")
        if score_key not in st.session_state and stored_score is not None:
            try:
                pct = round(float(stored_score) / profile.max_score() * 100, 1)
            except (ValueError, ZeroDivisionError):
                pct = None
            if pct is not None:
                st.metric("Score enregistré", f"{pct} %", (stored_classif or "").capitalize())
                st.caption("Recalcule pour voir le détail par critère.")

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
                    hubspot.update_score(contact_id, result.total, result.classification)
                    st.success("Score enregistré dans HubSpot.")
                except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                    st.error(f"Échec de l'enregistrement du score : {exc}")

    with tab_draft:
        draft_type = st.selectbox(
            "Type d'email", list(DRAFT_TYPES.keys()), format_func=lambda k: DRAFT_TYPES[k]
        )
        draft_instructions = st.text_area(
            "Consignes",
            placeholder="Informations ou instructions spécifiques pour cet email (ex. : mentionner une démo le 5 oct., ton informel, limiter à 3 phrases…)",
            height=80,
            key=f"draft_instructions_{contact_id}",
        )
        compare = st.toggle("Comparer avec GLM")
        drafts_key = f"drafts_{contact_id}_{draft_type}_{compare}"

        if st.button("Générer", icon=":material/edit:"):
            with st.spinner("Rédaction en cours..."):
                if compare:
                    st.session_state[drafts_key] = compare_drafts(
                        context, profile, draft_type, [claude, GLMBackend()], draft_instructions
                    )
                else:
                    st.session_state[drafts_key] = {
                        claude.name: generate_draft(context, profile, draft_type, claude, draft_instructions)
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
                        _save_note(contact_id, st.session_state[area_key], prefix=_LC_DRAFT_PREFIX)

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
