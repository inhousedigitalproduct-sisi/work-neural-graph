from __future__ import annotations

import logging

import streamlit as st

from src.utils.config import get_config
from src.utils.logging import configure_logging

config = get_config()
configure_logging(config.log_level)
logger = logging.getLogger(__name__)
logger.info("Application startup")

st.set_page_config(page_title="Work Neural Graph", layout="wide")

navigation = st.navigation(
    [
        st.Page("pages/1_Load_Data.py", title="Load Data", default=True),
        st.Page("pages/2_Neural_Graph.py", title="Neural Graph"),
        st.Page("pages/3_Fragmentation.py", title="Fragmentation Analysis"),
        st.Page("pages/5_Quality_Audit.py", title="Audit Kualitas"),
    ]
)
navigation.run()
