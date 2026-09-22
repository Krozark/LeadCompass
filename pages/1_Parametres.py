from __future__ import annotations

from pathlib import Path

import streamlit as st

from leadcompass.config import (
    BusinessProfile,
    ScoringCriterion,
    load_business_profile,
    save_business_profile,
)
from leadcompass.llm.claude_cli import ClaudeCLIBackend, ClaudeCLIError
from leadcompass.tasks.profile_generation import generate_profile_from_folders

st.set_page_config(page_title="LeadCompass — Paramètres", page_icon="⚙️")
st.title("⚙️ Paramètres — Profil entreprise")
st.caption(
    "Ces informations sont enregistrées dans config/business_profile.yaml (non versionné) "
    "et injectées dans chaque tâche IA pour que les réponses soient pertinentes."
)

saved_profile = load_business_profile()

st.subheader("Génération automatique depuis des dossiers")
st.caption(
    "Donne un ou plusieurs dossiers contenant des documents sur l'entreprise "
    "(présentation, documentation produit, site exporté...). Claude les explore "
    "en lecture seule — aucun fichier n'est modifié — et propose une mise à jour "
    "du profil ci-dessous, à valider avant d'enregistrer."
)
folders_text = st.text_area("Un chemin de dossier par ligne", height=80, key="folders_input")

if st.button("Analyser les dossiers"):
    directories = [line.strip() for line in folders_text.strip().splitlines() if line.strip()]
    invalid = [d for d in directories if not Path(d).expanduser().is_dir()]

    if not directories:
        st.warning("Indique au moins un dossier.")
    elif invalid:
        st.error("Dossier(s) introuvable(s) : " + ", ".join(invalid))
    else:
        resolved = [str(Path(d).expanduser().resolve()) for d in directories]
        try:
            with st.spinner("Analyse en cours (peut prendre plusieurs minutes)..."):
                st.session_state["generated_profile"] = generate_profile_from_folders(
                    resolved, saved_profile, ClaudeCLIBackend()
                )
            st.success("Profil généré ci-dessous — vérifie-le puis enregistre-le.")
        except ClaudeCLIError as exc:
            st.error(f"Échec de l'analyse : {exc}")

profile = st.session_state.get("generated_profile", saved_profile)

st.divider()

with st.form("business_profile_form"):
    name = st.text_input("Nom de l'entreprise", value=profile.name)
    product_description = st.text_area(
        "Description du produit/service", value=profile.product_description
    )
    target_customer = st.text_area("Client cible", value=profile.target_customer)
    value_proposition = st.text_area("Proposition de valeur", value=profile.value_proposition)
    tone = st.text_input("Ton de communication", value=profile.tone)

    st.subheader("Grille de score de pertinence")
    st.caption("Un critère par ligne, au format : Nom | Description | Poids")
    criteria_text = st.text_area(
        "Critères",
        value="\n".join(
            f"{c.name} | {c.description} | {c.weight}" for c in profile.scoring_criteria
        ),
        height=200,
        label_visibility="collapsed",
    )

    submitted = st.form_submit_button("Enregistrer")

if submitted:
    criteria = []
    skipped_lines = []
    for line in criteria_text.strip().splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        weight = None
        if len(parts) == 3:
            try:
                weight = float(parts[2].replace(",", "."))
            except ValueError:
                weight = None
        if len(parts) == 3 and weight is not None:
            criteria.append(ScoringCriterion(parts[0], parts[1], weight))
        else:
            skipped_lines.append(line)

    new_profile = BusinessProfile(
        name=name,
        product_description=product_description,
        target_customer=target_customer,
        value_proposition=value_proposition,
        tone=tone,
        scoring_criteria=criteria,
    )
    save_business_profile(new_profile)
    st.session_state.pop("generated_profile", None)
    st.success("Profil enregistré.")
    if skipped_lines:
        st.warning(
            "Lignes de critères ignorées (format attendu : Nom | Description | Poids) :\n"
            + "\n".join(f"- {line}" for line in skipped_lines)
        )
