from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="LeadCompass", page_icon=":material/explore:", layout="wide")

page = st.navigation(
    [
        st.Page("app_pages/prospects.py", title="Prospects", icon=":material/people:"),
        st.Page("app_pages/parametres.py", title="Paramètres", icon=":material/settings:"),
    ]
)
page.run()
