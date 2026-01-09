"""
Pipeline Page

Run and monitor the classification pipeline.
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import time

# Add parent dir to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api_client import FeedForwardAPI

st.set_page_config(page_title="Pipeline - FeedForward", page_icon="🔄", layout="wide")

# Initialize API client
if "api" not in st.session_state:
    st.session_state.api = FeedForwardAPI()

api = st.session_state.api


def main():
    st.title("Pipeline")
    st.markdown("Run and monitor the classification pipeline")

    # Check for active run
    try:
        active = api.get_active_run()
    except Exception as e:
        st.error(f"Cannot connect to API: {e}")
        st.stop()

    # Run configuration section
    st.subheader("Run Pipeline")

    if active["active"]:
        st.warning(f"Pipeline run #{active['run_id']} is currently active")

        # Show live status
        if st.button("Refresh Status"):
            st.rerun()

        try:
            status = api.get_pipeline_status(active["run_id"])
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Status", status["status"].upper())
            with col2:
                st.metric("Fetched", status["conversations_fetched"])
            with col3:
                st.metric("Classified", status["conversations_classified"])
            with col4:
                st.metric("Duration", f"{status.get('duration_seconds', 0):.0f}s")
        except Exception as e:
            st.error(f"Failed to get status: {e}")
    else:
        # Run configuration form
        with st.form("run_config"):
            col1, col2 = st.columns(2)

            with col1:
                days = st.slider(
                    "Days to look back",
                    min_value=1,
                    max_value=30,
                    value=7,
                    help="How many days of conversations to process"
                )

                max_convs = st.number_input(
                    "Max conversations (0 = unlimited)",
                    min_value=0,
                    max_value=1000,
                    value=0,
                    help="Limit for testing. Set to 0 for all conversations."
                )

            with col2:
                dry_run = st.checkbox(
                    "Dry run",
                    value=False,
                    help="Classify but don't store results"
                )

                concurrency = st.slider(
                    "Concurrency",
                    min_value=1,
                    max_value=50,
                    value=20,
                    help="Parallel API calls (higher = faster but more load)"
                )

            submitted = st.form_submit_button("Start Pipeline Run", type="primary")

            if submitted:
                try:
                    result = api.run_pipeline(
                        days=days,
                        max_conversations=max_convs if max_convs > 0 else None,
                        dry_run=dry_run,
                        concurrency=concurrency,
                    )
                    st.success(f"Pipeline started! Run ID: {result['run_id']}")
                    st.info(result["message"])
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to start pipeline: {e}")

    st.markdown("---")

    # Run history section
    st.subheader("Run History")

    try:
        history = api.get_pipeline_history(limit=20)
    except Exception as e:
        st.error(f"Failed to load history: {e}")
        history = []

    if history:
        rows = []
        for run in history:
            started = datetime.fromisoformat(run["started_at"].replace("Z", "+00:00"))
            completed = None
            if run["completed_at"]:
                completed = datetime.fromisoformat(run["completed_at"].replace("Z", "+00:00"))

            rows.append({
                "ID": run["id"],
                "Started": started.strftime("%Y-%m-%d %H:%M"),
                "Completed": completed.strftime("%H:%M") if completed else "-",
                "Status": run["status"].upper(),
                "Fetched": run["conversations_fetched"],
                "Classified": run["conversations_classified"],
                "Stored": run["conversations_stored"],
                "Duration": f"{run['duration_seconds']:.0f}s" if run["duration_seconds"] else "-",
            })

        df = pd.DataFrame(rows)

        # Color-code status
        def highlight_status(row):
            if row["Status"] == "COMPLETED":
                return [""] * len(row)
            elif row["Status"] == "RUNNING":
                return ["background-color: #fff3cd"] * len(row)
            elif row["Status"] == "FAILED":
                return ["background-color: #f8d7da"] * len(row)
            return [""] * len(row)

        styled_df = df.style.apply(highlight_status, axis=1)
        st.dataframe(styled_df, use_container_width=True, hide_index=True)

        # Detail view for selected run
        st.markdown("### Run Details")
        run_ids = [r["id"] for r in history]
        selected_id = st.selectbox("Select run to view details", run_ids)

        if selected_id:
            try:
                detail = api.get_pipeline_status(selected_id)

                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Status:** {detail['status'].upper()}")
                    st.write(f"**Started:** {detail['started_at']}")
                    st.write(f"**Completed:** {detail.get('completed_at', 'In progress')}")
                    if detail.get("date_from"):
                        st.write(f"**Date range:** {detail['date_from'][:10]} to {detail['date_to'][:10]}")

                with col2:
                    st.write(f"**Fetched:** {detail['conversations_fetched']}")
                    st.write(f"**Filtered:** {detail['conversations_filtered']}")
                    st.write(f"**Classified:** {detail['conversations_classified']}")
                    st.write(f"**Stored:** {detail['conversations_stored']}")

                if detail.get("error_message"):
                    st.error(f"Error: {detail['error_message']}")

            except Exception as e:
                st.error(f"Failed to load run details: {e}")
    else:
        st.info("No pipeline runs yet. Start one above!")


if __name__ == "__main__":
    main()
