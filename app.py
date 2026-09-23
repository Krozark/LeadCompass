from __future__ import annotations

import streamlit as st

from leadcompass.config import load_llm_choice, save_llm_choice
from leadcompass.llm.registry import configured_backends, default_backend_name

st.set_page_config(page_title="LeadCompass", page_icon=":material/explore:", layout="wide")

# ── Default LLM selector, shown at the top of every page ─────────────────────
backends = configured_backends()
if backends:
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption("Modèle IA :")
        choice = st.segmented_control(
            "Modèle IA par défaut",
            options=list(backends),
            default=default_backend_name(),
            required=True,
            label_visibility="collapsed",
        )
    st.session_state["default_backend_name"] = choice
    if choice != load_llm_choice():
        save_llm_choice(choice)
else:
    st.warning(
        "Aucun modèle IA disponible : vérifie la liste des modèles sur la page Paramètres "
        "(binaire CLI installé et détecté)."
    )

page = st.navigation(
    [
        st.Page("app_pages/prospects.py", title="Prospects", icon=":material/people:"),
        st.Page("app_pages/decouverte.py", title="Découverte", icon=":material/travel_explore:"),
        st.Page("app_pages/parametres.py", title="Paramètres", icon=":material/settings:"),
    ]
)
page.run()
