from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd
import streamlit as st

from leadcompass.config import (
    BusinessProfile,
    LLMBackendConfig,
    ScoringCriterion,
    load_business_profile,
    load_llm_backends,
    save_business_profile,
    save_llm_backends,
)
from leadcompass.llm.claude_cli import ClaudeCLIError
from leadcompass.llm.registry import configured_backends, default_backend_name, get_backend
from leadcompass.tasks.profile_generation import generate_profile_from_folders

st.title("Paramètres")

# ── Modèles IA ────────────────────────────────────────────────────────────────
st.subheader("Modèles IA")
st.caption(
    "Chaque modèle est un CLI compatible Claude Code : `claude` directement, ou un wrapper "
    "pointant sur un autre fournisseur (ex. `claude-zai` pour les modèles GLM de Z.ai). "
    "Le sélecteur en haut de l'application permet ensuite de choisir à tout moment le modèle "
    "utilisé par défaut ; cette liste est enregistrée dans config/settings.yaml."
)

models_df = pd.DataFrame(
    [{"name": b.name, "cli_path": b.cli_path} for b in load_llm_backends()],
    columns=["name", "cli_path"],
)
edited_models = st.data_editor(
    models_df,
    num_rows="dynamic",
    hide_index=True,
    key="models_editor",
    column_config={
        "name": st.column_config.TextColumn("Nom affiché", required=True),
        "cli_path": st.column_config.TextColumn("Binaire à appeler", required=True),
    },
)

edited_models = edited_models.dropna(subset=["name", "cli_path"], how="all")
for _, row in edited_models.iterrows():
    name, cli_path = str(row["name"]).strip(), str(row["cli_path"]).strip()
    if not name or not cli_path:
        continue
    detected = shutil.which(cli_path) is not None
    state = "détecté" if detected else "binaire introuvable"
    icon = ":material/check_circle:" if detected else ":material/warning:"
    st.markdown(f"- {icon} **{name}** (`{cli_path}`) — {state}")

if st.button("Enregistrer les modèles", icon=":material/save:"):
    models = [
        LLMBackendConfig(str(row["name"]).strip(), str(row["cli_path"]).strip())
        for _, row in edited_models.iterrows()
        if str(row["name"]).strip() and str(row["cli_path"]).strip()
    ]
    names = [m.name for m in models]
    if not models:
        st.error("Indique au moins un modèle (nom et binaire).")
    elif len(names) != len(set(names)):
        st.error("Chaque modèle doit avoir un nom unique.")
    else:
        save_llm_backends(models)
        st.success("Modèles enregistrés.")

st.divider()

# ── Profil entreprise ─────────────────────────────────────────────────────────
st.subheader("Profil entreprise")
st.caption(
    "Ces informations sont enregistrées dans config/business_profile.yaml (non versionné) "
    "et injectées dans chaque tâche IA pour que les réponses soient pertinentes."
)

saved_profile = load_business_profile()

st.subheader("Génération automatique depuis des dossiers")
st.caption(
    "Donne un ou plusieurs dossiers contenant des documents sur l'entreprise "
    "(présentation, documentation produit, site exporté...). Le modèle sélectionné les explore "
    "en lecture seule — aucun fichier n'est modifié — et propose une mise à jour "
    "du profil ci-dessous, à valider avant d'enregistrer."
)
folders_df = pd.DataFrame({"chemin": pd.Series(dtype=str), "description": pd.Series(dtype=str)})
edited_folders = st.data_editor(
    folders_df,
    num_rows="dynamic",
    hide_index=True,
    column_config={
        "chemin": st.column_config.TextColumn("Chemin du dossier", required=True),
        "description": st.column_config.TextColumn(
            "Description / poids",
            help="Précise le contenu ou l'importance de ce dossier pour guider l'IA.",
        ),
    },
    key="folders_editor",
)

available_backends = configured_backends()
profile_llm_name = st.session_state.get("default_backend_name") or default_backend_name()
profile_llm = get_backend(profile_llm_name) if profile_llm_name in available_backends else None

if profile_llm is None:
    st.caption("Aucun modèle IA détecté — configure-en un dans la section Modèles IA ci-dessus.")

if st.button("Analyser les dossiers", icon=":material/folder_open:", disabled=profile_llm is None):
    raw_folders = [
        (str(row["chemin"]).strip(), str(row["description"]).strip() if pd.notna(row["description"]) else "")
        for _, row in edited_folders.iterrows()
        if str(row["chemin"]).strip()
    ]
    paths = [p for p, _ in raw_folders]
    invalid = [p for p in paths if not Path(p).expanduser().is_dir()]

    if not paths:
        st.warning("Indique au moins un dossier.")
    elif invalid:
        st.error("Dossier(s) introuvable(s) : " + ", ".join(invalid))
    else:
        resolved = [(str(Path(p).expanduser().resolve()), desc) for p, desc in raw_folders]
        try:
            with st.spinner("Analyse en cours (peut prendre plusieurs minutes)..."):
                st.session_state["generated_profile"] = generate_profile_from_folders(
                    resolved, saved_profile, profile_llm
                )
            st.success("Profil généré ci-dessous — vérifie-le puis enregistre-le.")
        except ClaudeCLIError as exc:
            st.error(f"Échec de l'analyse : {exc}")

profile = st.session_state.get("generated_profile", saved_profile)

st.divider()

with st.form("business_profile_form"):
    name = st.text_input("Nom de l'entreprise", value=profile.name)
    product_description = st.text_area("Description du produit/service", value=profile.product_description)
    target_customer = st.text_area("Client cible", value=profile.target_customer)
    value_proposition = st.text_area("Proposition de valeur", value=profile.value_proposition)
    tone = st.text_input("Ton de communication", value=profile.tone)

    st.subheader("Types de prospect")
    st.caption(
        "Liste des catégories disponibles pour qualifier vos prospects (ex. : B2C, Festival, Structure…)."
    )
    types_df = pd.DataFrame({"type": pd.Series(profile.prospect_types, dtype=str)})
    edited_types = st.data_editor(
        types_df,
        num_rows="dynamic",
        hide_index=True,
        column_config={"type": st.column_config.TextColumn("Type", required=True)},
    )

    st.subheader("Grille de score de pertinence")
    criteria_df = pd.DataFrame(
        [
            {"name": c.name, "description": c.description, "weight": c.weight}
            for c in profile.scoring_criteria
        ],
        columns=["name", "description", "weight"],
    )
    edited_criteria = st.data_editor(
        criteria_df,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "name": st.column_config.TextColumn("Nom", required=True),
            "description": st.column_config.TextColumn("Description", required=True),
            "weight": st.column_config.NumberColumn(
                "Poids", min_value=0.0, step=0.5, default=1.0, required=True
            ),
        },
    )

    submitted = st.form_submit_button("Enregistrer", icon=":material/save:")

if submitted:
    prospect_types = [
        str(row["type"]).strip() for _, row in edited_types.iterrows() if str(row["type"]).strip()
    ]
    criteria = [
        ScoringCriterion(str(row["name"]).strip(), str(row["description"]).strip(), float(row["weight"]))
        for _, row in edited_criteria.iterrows()
        if str(row["name"]).strip() and pd.notna(row["weight"])
    ]

    new_profile = BusinessProfile(
        name=name,
        product_description=product_description,
        target_customer=target_customer,
        value_proposition=value_proposition,
        tone=tone,
        scoring_criteria=criteria,
        prospect_types=prospect_types,
    )
    save_business_profile(new_profile)
    st.session_state.pop("generated_profile", None)
    st.success("Profil enregistré.")
