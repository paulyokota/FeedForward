"""
Dashboard Page

Overview metrics and recent activity for FeedForward pipeline.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# Add parent dir to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api_client import FeedForwardAPI

st.set_page_config(page_title="Dashboard - FeedForward", page_icon="📊", layout="wide")

# Initialize API client
if "api" not in st.session_state:
    st.session_state.api = FeedForwardAPI()

api = st.session_state.api


def format_number(n: int) -> str:
    """Format number with commas."""
    return f"{n:,}"


def main():
    st.title("Dashboard")
    st.markdown("Overview of pipeline activity and metrics")

    # Fetch dashboard data
    try:
        metrics = api.get_dashboard_metrics(days=30)
    except Exception as e:
        st.error(f"Failed to load dashboard: {e}")
        st.info("Make sure the API is running: `uvicorn src.api.main:app --reload`")
        st.stop()

    # Top-level metrics
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Conversations",
            format_number(metrics["total_conversations"]),
        )

    with col2:
        st.metric(
            "Last 7 Days",
            format_number(metrics["conversations_last_7_days"]),
        )

    with col3:
        st.metric(
            "Total Themes",
            format_number(metrics["total_themes"]),
        )

    with col4:
        st.metric(
            "Trending Themes",
            format_number(metrics["trending_themes_count"]),
            help="Themes with 2+ occurrences in last 7 days"
        )

    st.markdown("---")

    # Two-column layout for details
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Classification Metrics")

        # Confidence distribution
        st.markdown("**Stage 2 Confidence Distribution**")
        s2_conf = metrics["stage2_confidence"]
        conf_data = {
            "Level": ["High", "Medium", "Low"],
            "Count": [s2_conf["high"], s2_conf["medium"], s2_conf["low"]],
        }
        conf_df = pd.DataFrame(conf_data)
        st.bar_chart(conf_df.set_index("Level"))

        # Additional metrics
        st.markdown("**Analysis Metrics**")
        st.write(f"- Classification changes (Stage 1 → 2): **{metrics['classification_changes']}**")
        st.write(f"- High disambiguation: **{metrics['disambiguation_high_count']}**")
        st.write(f"- Resolutions detected: **{metrics['resolution_detected_count']}**")
        st.write(f"- Orphan themes: **{metrics['orphan_themes_count']}**")

    with right_col:
        st.subheader("Top Conversation Types")

        types = metrics["top_conversation_types"]
        if types:
            type_df = pd.DataFrame([
                {"Type": k.replace("_", " ").title(), "Count": v}
                for k, v in types.items()
            ])
            st.bar_chart(type_df.set_index("Type"))
        else:
            st.info("No classification data available")

        st.subheader("Recent Pipeline Runs")

        runs = metrics["recent_runs"]
        if runs:
            runs_data = []
            for run in runs:
                started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
                runs_data.append({
                    "ID": run["id"],
                    "Started": started.strftime("%Y-%m-%d %H:%M"),
                    "Status": run["status"].upper(),
                    "Fetched": run["conversations_fetched"],
                    "Stored": run["conversations_stored"],
                })
            runs_df = pd.DataFrame(runs_data)
            st.dataframe(runs_df, use_container_width=True, hide_index=True)
        else:
            st.info("No pipeline runs yet")

        if metrics["last_run_at"]:
            last_run = datetime.fromisoformat(metrics["last_run_at"].replace("Z", "+00:00"))
            st.caption(f"Last run: {last_run.strftime('%Y-%m-%d %H:%M UTC')}")


if __name__ == "__main__":
    main()
