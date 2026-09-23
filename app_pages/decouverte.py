from __future__ import annotations

import streamlit as st

from leadcompass.config import load_business_profile
from leadcompass.hubspot_client import HubSpotClient, HubSpotError
from leadcompass.llm.claude_cli import ClaudeCLIError
from leadcompass.llm.registry import configured_backends, default_backend_name, get_backend
from leadcompass.tasks.discovery import discover_prospects, split_known_leads

st.title("Découverte")
st.caption(
    "Décris qui tu cherches — prospects, influenceurs, partenaires... — le modèle sélectionné "
    "explore le web et propose des contacts réels et sourcés, que tu peux ensuite ajouter à HubSpot."
)

profile = load_business_profile()
if not profile.is_configured:
    st.warning(
        "Le profil entreprise n'est pas configuré — les résultats seront moins pertinents. "
        "Renseigne-le sur la page Paramètres."
    )


@st.cache_resource
def _get_hubspot_client() -> HubSpotClient:
    return HubSpotClient()


try:
    hubspot = _get_hubspot_client()
except HubSpotError as exc:
    st.error(f"Configuration HubSpot manquante : {exc}")
    st.stop()

_LC_DISCOVERY_PREFIX = "[LeadCompass:découverte] "


def _known_contact_keys() -> tuple[set[str], set[str]]:
    """(emails, identités nom/entreprise) de tous les contacts HubSpot, normalisés."""
    emails: set[str] = set()
    identities: set[str] = set()
    after: str | None = None
    for _ in range(50):  # garde-fou : ~5 000 contacts maximum
        page, after = hubspot.list_contacts(limit=100, after=after)
        for contact in page:
            props = contact.get("properties", {})
            if props.get("email"):
                emails.add(" ".join(props["email"].lower().split()))
            for value in (
                f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                props.get("company") or "",
            ):
                if value.strip():
                    identities.add(" ".join(value.lower().split()))
        if not after:
            break
    return emails, identities


guide = st.text_area(
    "Qui cherches-tu ?",
    placeholder=(
        "Ex. : festivals de musique en Bretagne avec une programmation jazz ; "
        "influenceurs LinkedIn sur la data B2B ; PME industrielles en Auvergne..."
    ),
    height=100,
)
count = st.number_input("Nombre de résultats", min_value=3, max_value=20, value=10, step=1)

backends = configured_backends()
llm_name = st.session_state.get("default_backend_name") or default_backend_name()
# Web research needs many tool turns; give the CLI more room than a simple draft.
llm = get_backend(llm_name, max_turns=15, timeout=600) if llm_name in backends else None

if llm is None:
    st.caption("Aucun modèle IA détecté — configure-en un sur la page Paramètres.")

# Disabled only on missing backend: gating on `guide` here would keep the button
# greyed while the text is typed, because Streamlit commits a text area's value
# only when it loses focus — and a disabled button swallows that first click.
if st.button("Lancer la recherche", icon=":material/travel_explore:", disabled=llm is None):
    if not guide.strip():
        st.warning("Décris d'abord qui tu cherches pour guider la recherche.")
    else:
        try:
            with st.spinner("Recherche sur le web (peut prendre plusieurs minutes)..."):
                for key in list(st.session_state):
                    if key.startswith("discovery_added_"):
                        del st.session_state[key]
                known_emails, known_identities = set(), set()
                try:
                    known_emails, known_identities = _known_contact_keys()
                except Exception as exc:  # noqa: BLE001 - la recherche peut continuer sans filtre
                    st.warning(f"Impossible de vérifier les doublons HubSpot : {exc}")
                results, hidden = split_known_leads(
                    discover_prospects(
                        guide,
                        profile,
                        llm,
                        int(count),
                        known_identities=sorted(known_identities) or None,
                    ),
                    known_emails,
                    known_identities,
                )
                st.session_state["discovery"] = {
                    "guide": guide.strip(),
                    "results": results,
                    "hidden": hidden,
                }
        except ValueError as exc:
            st.error(f"Réponse du modèle inexploitable : {exc}")
        except ClaudeCLIError as exc:
            st.error(f"Échec de la recherche : {exc}")

data = st.session_state.get("discovery")
if data:
    hidden = data.get("hidden", 0)
    if hidden:
        st.caption(f"{hidden} résultat(s) déjà présents dans HubSpot ont été masqués.")
    if not data["results"]:
        if hidden:
            st.info("Tous les résultats trouvés sont déjà dans HubSpot.")
        else:
            st.info("Aucun résultat trouvé pour cette recherche.")
    else:
        st.subheader(f"{len(data['results'])} contact(s) trouvé(s)")
        st.caption(f"Recherche : {data['guide']}")
        st.divider()

        for idx, lead in enumerate(data["results"]):
            name = lead.get("name") or "—"
            org_role = " · ".join(x for x in (lead.get("organization"), lead.get("role")) if x)
            label = f"{name}  ·  {org_role}" if org_role else name

            with st.expander(label):
                cols = st.columns([3, 1])
                with cols[0]:
                    if lead.get("why_relevant"):
                        st.markdown(f"**Pourquoi pertinent**  \n{lead['why_relevant']}")
                    if lead.get("email"):
                        st.markdown(f"**Email**  \n{lead['email']}")
                with cols[1]:
                    if lead.get("website"):
                        st.link_button("Ouvrir la source", lead["website"])

                added_key = f"discovery_added_{idx}"
                if st.session_state.get(added_key):
                    st.success("Ajouté à HubSpot.")
                    continue
                if st.button("Ajouter à HubSpot", key=f"discovery_add_{idx}", icon=":material/person_add:"):
                    parts = name.split()
                    props = {
                        "firstname": parts[0] if parts else "",
                        "lastname": " ".join(parts[1:]) if len(parts) > 1 else "",
                        "company": lead.get("organization", ""),
                        "jobtitle": lead.get("role", ""),
                    }
                    if lead.get("email"):
                        props["email"] = lead["email"]
                    try:
                        contact = hubspot.create_contact(props)
                        hubspot.create_note(
                            contact["id"],
                            _LC_DISCOVERY_PREFIX
                            + f"Trouvé via une recherche guidée : {data['guide']}\n"
                            + f"Pertinence : {lead.get('why_relevant', '—')}\n"
                            + f"Source : {lead.get('website') or '—'}",
                        )
                        st.session_state[added_key] = True
                        st.success("Contact créé dans HubSpot.")
                    except HubSpotError as exc:
                        st.error(f"Échec de la création : {exc}")
                    except Exception as exc:  # noqa: BLE001 - surfaced to the user, not swallowed
                        st.error(f"Échec de la création : {exc}")
