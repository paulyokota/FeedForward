"""
FeedForward Dashboard

Streamlit application for operational visibility into the
FeedForward conversation analysis pipeline.

Run with:
    streamlit run frontend/app.py

Requires FastAPI backend running on localhost:8000
"""

import streamlit as st

# Page config must be first Streamlit command
st.set_page_config(
    page_title="FeedForward",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from api_client import FeedForwardAPI

# Initialize API client in session state
if "api" not in st.session_state:
    st.session_state.api = FeedForwardAPI()


def main():
    """Main app entry point."""
    st.title("FeedForward")
    st.markdown("*Conversation analysis pipeline dashboard*")

    # Check API health
    api = st.session_state.api
    try:
        health = api.health_full()
        if health["status"] == "healthy":
            st.success("API connected")
        else:
            st.warning(f"API status: {health['status']}")
    except Exception as e:
        st.error(f"Cannot connect to API at {api.base_url}")
        st.info("Start the API with: `uvicorn src.api.main:app --reload --port 8000`")
        st.stop()

    st.markdown("---")
    st.markdown("""
    ### Quick Links

    Use the sidebar to navigate:
    - **Dashboard** - Overview metrics and recent activity
    - **Pipeline** - Run and monitor classification pipeline
    - **Themes** - Browse trending themes and orphans

    ### API Documentation

    FastAPI docs available at:
    - [Swagger UI](http://localhost:8000/docs)
    - [ReDoc](http://localhost:8000/redoc)
    """)


if __name__ == "__main__":
    main()
