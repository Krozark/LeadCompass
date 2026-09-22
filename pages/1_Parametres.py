from __future__ import annotations

import streamlit as st

from leadcompass.config import (
    BusinessProfile,
    ScoringCriterion,
    load_business_profile,
    save_business_profile,
)

st.set_page_config(page_title="LeadCompass — Paramètres", page_icon="⚙️")
st.title("⚙️ Paramètres — Profil entreprise")
st.caption(
    "Ces informations sont enregistrées dans config/business_profile.yaml (non versionné) "
    "et injectées dans chaque tâche IA pour que les réponses soient pertinentes."
)

profile = load_business_profile()

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
    for line in criteria_text.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if len(parts) == 3:
            criteria.append(ScoringCriterion(parts[0], parts[1], float(parts[2])))

    new_profile = BusinessProfile(
        name=name,
        product_description=product_description,
        target_customer=target_customer,
        value_proposition=value_proposition,
        tone=tone,
        scoring_criteria=criteria,
    )
    save_business_profile(new_profile)
    st.success("Profil enregistré.")
