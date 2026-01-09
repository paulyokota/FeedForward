"""
Themes Page

Browse trending themes and orphans.
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# Add parent dir to path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from api_client import FeedForwardAPI

st.set_page_config(page_title="Themes - FeedForward", page_icon="🏷️", layout="wide")

# Initialize API client
if "api" not in st.session_state:
    st.session_state.api = FeedForwardAPI()

api = st.session_state.api


def format_theme_row(theme: dict) -> dict:
    """Format theme data for table display."""
    last_seen = datetime.fromisoformat(theme["last_seen_at"].replace("Z", "+00:00"))
    return {
        "Signature": theme["issue_signature"],
        "Product Area": theme["product_area"],
        "Component": theme["component"],
        "Count": theme["occurrence_count"],
        "Last Seen": last_seen.strftime("%Y-%m-%d"),
        "Ticket": "✓" if theme["ticket_created"] else "-",
    }


def main():
    st.title("Themes")
    st.markdown("Browse extracted themes from conversations")

    # Tab navigation
    tab1, tab2, tab3 = st.tabs(["Trending", "Orphans", "All Themes"])

    # Trending themes tab
    with tab1:
        st.subheader("Trending Themes")
        st.markdown("Themes with multiple occurrences in recent conversations")

        col1, col2, col3 = st.columns(3)
        with col1:
            trend_days = st.selectbox("Time window", [7, 14, 30], index=0, key="trend_days")
        with col2:
            min_occ = st.selectbox("Min occurrences", [2, 3, 5], index=0, key="min_occ")
        with col3:
            trend_limit = st.selectbox("Show top", [10, 20, 50], index=1, key="trend_limit")

        try:
            trending = api.get_trending_themes(
                days=trend_days,
                min_occurrences=min_occ,
                limit=trend_limit
            )
            themes = trending["themes"]

            if themes:
                st.metric("Trending Themes", len(themes))

                rows = [format_theme_row(t) for t in themes]
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Detail view
                st.markdown("### Theme Details")
                signatures = [t["issue_signature"] for t in themes]
                selected = st.selectbox("Select theme", signatures, key="trend_select")

                if selected:
                    theme = next(t for t in themes if t["issue_signature"] == selected)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Signature:** `{theme['issue_signature']}`")
                        st.write(f"**Product Area:** {theme['product_area']}")
                        st.write(f"**Component:** {theme['component']}")
                        st.write(f"**Occurrences:** {theme['occurrence_count']}")
                    with col2:
                        st.write(f"**User Intent:** {theme.get('sample_user_intent', 'N/A')}")
                        st.write(f"**Symptoms:** {', '.join(theme.get('sample_symptoms', []))}")
                        st.write(f"**Root Cause:** {theme.get('sample_root_cause_hypothesis', 'N/A')}")
            else:
                st.info("No trending themes found for the selected criteria")

        except Exception as e:
            st.error(f"Failed to load trending themes: {e}")

    # Orphans tab
    with tab2:
        st.subheader("Orphan Themes")
        st.markdown("Low-count themes that may need review or merging")

        col1, col2 = st.columns(2)
        with col1:
            orphan_days = st.selectbox("From last N days", [7, 14, 30, 60], index=2, key="orphan_days")
        with col2:
            show_singletons = st.checkbox("Only singletons (count=1)", value=False)

        try:
            if show_singletons:
                result = api.get_singleton_themes(days=orphan_days, limit=50)
            else:
                result = api.get_orphan_themes(threshold=3, days=orphan_days, limit=50)

            themes = result["themes"]

            if themes:
                st.metric("Orphan Themes", len(themes))

                rows = [format_theme_row(t) for t in themes]
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Summary by product area
                st.markdown("### By Product Area")
                area_counts = {}
                for t in themes:
                    area = t["product_area"] or "Unknown"
                    area_counts[area] = area_counts.get(area, 0) + 1

                area_df = pd.DataFrame([
                    {"Product Area": k, "Orphan Count": v}
                    for k, v in sorted(area_counts.items(), key=lambda x: -x[1])
                ])
                st.bar_chart(area_df.set_index("Product Area"))
            else:
                st.success("No orphan themes! All themes have multiple occurrences.")

        except Exception as e:
            st.error(f"Failed to load orphan themes: {e}")

    # All themes tab
    with tab3:
        st.subheader("All Themes")
        st.markdown("Complete theme list with filtering")

        # Filters
        col1, col2 = st.columns(2)
        with col1:
            # Get unique product areas
            try:
                all_themes = api.list_themes(limit=200)
                product_areas = sorted(set(
                    t["product_area"] for t in all_themes["themes"]
                    if t["product_area"]
                ))
                product_areas = ["All"] + product_areas
            except:
                product_areas = ["All"]

            selected_area = st.selectbox("Product Area", product_areas, key="all_area")
        with col2:
            all_limit = st.selectbox("Show", [25, 50, 100], index=1, key="all_limit")

        try:
            area_filter = None if selected_area == "All" else selected_area
            result = api.list_themes(product_area=area_filter, limit=all_limit)
            themes = result["themes"]

            st.metric("Total Themes", result["total"])

            if themes:
                rows = [format_theme_row(t) for t in themes]
                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No themes found")

        except Exception as e:
            st.error(f"Failed to load themes: {e}")


if __name__ == "__main__":
    main()
