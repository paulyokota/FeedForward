"""
Theme Labeling UI for VDD

Label conversations with themes to build ground truth fixtures.
Supports selecting existing themes or creating new ones.

Run with: streamlit run tools/theme_labeler.py
"""

import json
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.connection import get_connection

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
VOCAB_FILE = Path(__file__).parent.parent / "config" / "theme_vocabulary.json"
FIXTURES_FILE = DATA_DIR / "theme_fixtures.json"


def load_vocabulary() -> dict:
    """Load theme vocabulary."""
    with open(VOCAB_FILE) as f:
        return json.load(f)


def save_vocabulary(vocab: dict) -> None:
    """Save theme vocabulary."""
    with open(VOCAB_FILE, "w") as f:
        json.dump(vocab, f, indent=2)


def load_fixtures() -> dict:
    """Load existing fixtures."""
    if FIXTURES_FILE.exists():
        with open(FIXTURES_FILE) as f:
            return json.load(f)
    return {
        "version": "1.0",
        "description": "Ground truth fixtures for theme extraction validation.",
        "acceptance_criteria": {
            "accuracy_threshold": 1.0,
            "description": "All fixtures must match expected_theme exactly"
        },
        "fixtures": []
    }


def save_fixtures(data: dict) -> None:
    """Save fixtures."""
    with open(FIXTURES_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_conversations(limit: int = 100, offset: int = 0) -> list[dict]:
    """Get conversations from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT c.id, c.created_at, c.source_body, c.issue_type,
                       c.sentiment, c.churn_risk, c.priority,
                       t.issue_signature as current_theme
                FROM conversations c
                LEFT JOIN themes t ON t.conversation_id = c.id
                WHERE c.source_body IS NOT NULL
                  AND LENGTH(c.source_body) > 30
                ORDER BY c.created_at DESC
                LIMIT %s OFFSET %s
            """, (limit, offset))
            rows = cur.fetchall()

            return [{
                "id": str(row[0]),
                "created_at": row[1],
                "source_body": row[2],
                "issue_type": row[3],
                "sentiment": row[4],
                "churn_risk": row[5],
                "priority": row[6],
                "current_theme": row[7],
            } for row in rows]


def get_fixture_ids(fixtures: dict) -> set:
    """Get IDs of already-labeled fixtures."""
    return {f["id"] for f in fixtures.get("fixtures", [])}


def main():
    st.set_page_config(page_title="Theme Labeler", layout="wide")
    st.title("Theme Labeler")
    st.caption("Label conversations with themes to build VDD fixtures")

    # Load data
    vocab = load_vocabulary()
    fixtures_data = load_fixtures()
    existing_ids = get_fixture_ids(fixtures_data)

    # Theme list from vocabulary
    theme_signatures = sorted(vocab["themes"].keys())

    # Sidebar: Stats and new theme creation
    with st.sidebar:
        st.header("Stats")
        st.metric("Fixtures", len(fixtures_data["fixtures"]))
        st.metric("Vocabulary Themes", len(theme_signatures))

        st.divider()

        # Create new theme
        st.header("Create New Theme")
        with st.form("new_theme"):
            new_sig = st.text_input("Signature (snake_case)", placeholder="e.g., pin_design_question")
            new_desc = st.text_area("Description", placeholder="What this theme captures...")
            new_area = st.selectbox("Product Area", [
                "pinterest_publishing", "scheduling", "ai_creation", "billing",
                "account", "analytics", "integrations", "communities", "other"
            ])
            new_component = st.text_input("Component", placeholder="e.g., scheduler, oauth, dashboard")
            new_keywords = st.text_input("Keywords (comma-separated)", placeholder="e.g., pin, design, create")
            new_fix = st.text_input("Engineering Fix", placeholder="What would fix this issue type?")

            if st.form_submit_button("Add Theme"):
                if new_sig and new_desc:
                    if new_sig in vocab["themes"]:
                        st.error(f"Theme '{new_sig}' already exists!")
                    else:
                        vocab["themes"][new_sig] = {
                            "issue_signature": new_sig,
                            "product_area": new_area,
                            "component": new_component or "unknown",
                            "description": new_desc,
                            "keywords": [k.strip() for k in new_keywords.split(",") if k.strip()],
                            "example_intents": [],
                            "engineering_fix": new_fix or "TBD",
                            "status": "active",
                            "merged_into": None,
                            "created_at": datetime.now().isoformat(),
                            "updated_at": datetime.now().isoformat(),
                        }
                        save_vocabulary(vocab)
                        st.success(f"Added theme: {new_sig}")
                        st.rerun()
                else:
                    st.warning("Signature and description required")

    # Main area: Conversation labeling
    col1, col2 = st.columns([2, 1])

    with col1:
        st.header("Conversations")

        # Pagination
        page = st.number_input("Page", min_value=1, value=1)
        per_page = 20
        offset = (page - 1) * per_page

        # Filter options
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            show_labeled = st.checkbox("Show already labeled", value=False)
        with filter_col2:
            filter_theme = st.selectbox("Filter by current theme", ["All"] + theme_signatures)

        conversations = get_conversations(limit=per_page, offset=offset)

        # Filter
        if not show_labeled:
            conversations = [c for c in conversations if c["id"] not in existing_ids]
        if filter_theme != "All":
            conversations = [c for c in conversations if c["current_theme"] == filter_theme]

        if not conversations:
            st.info("No conversations to show. Try different filters or page.")

        for conv in conversations:
            is_labeled = conv["id"] in existing_ids
            status = "✅ Labeled" if is_labeled else ""

            with st.expander(f"{conv['id'][:12]}... | {conv['current_theme'] or 'No theme'} {status}"):
                st.markdown(f"**Message:**")
                st.text(conv["source_body"][:500] + ("..." if len(conv["source_body"]) > 500 else ""))

                st.markdown(f"**Current classification:** issue_type={conv['issue_type']}, sentiment={conv['sentiment']}")
                st.markdown(f"**Current theme:** `{conv['current_theme']}`")

                # Labeling form
                st.divider()

                selected_theme = st.selectbox(
                    "Correct theme:",
                    theme_signatures,
                    index=theme_signatures.index(conv["current_theme"]) if conv["current_theme"] in theme_signatures else 0,
                    key=f"theme_{conv['id']}"
                )

                rationale = st.text_input(
                    "Rationale (why this theme?):",
                    key=f"rationale_{conv['id']}",
                    placeholder="e.g., User is asking about X, not Y"
                )

                if st.button("Save as Fixture", key=f"save_{conv['id']}"):
                    if not rationale:
                        st.warning("Please add a rationale")
                    else:
                        # Remove existing fixture for this ID if any
                        fixtures_data["fixtures"] = [
                            f for f in fixtures_data["fixtures"] if f["id"] != conv["id"]
                        ]

                        # Add new fixture
                        fixtures_data["fixtures"].append({
                            "id": conv["id"],
                            "source_body": conv["source_body"],
                            "issue_type": conv["issue_type"],
                            "sentiment": conv["sentiment"],
                            "churn_risk": conv["churn_risk"],
                            "priority": conv["priority"],
                            "expected_theme": selected_theme,
                            "rationale": rationale,
                        })

                        save_fixtures(fixtures_data)
                        st.success(f"Saved fixture: {conv['id']} → {selected_theme}")
                        st.rerun()

    with col2:
        st.header("Current Fixtures")

        if fixtures_data["fixtures"]:
            for fixture in fixtures_data["fixtures"]:
                with st.container():
                    st.markdown(f"**{fixture['expected_theme']}**")
                    st.caption(f"ID: {fixture['id'][:12]}...")
                    st.caption(fixture["source_body"][:100] + "...")
                    st.caption(f"_Rationale: {fixture.get('rationale', 'N/A')}_")

                    if st.button("Remove", key=f"remove_{fixture['id']}"):
                        fixtures_data["fixtures"] = [
                            f for f in fixtures_data["fixtures"] if f["id"] != fixture["id"]
                        ]
                        save_fixtures(fixtures_data)
                        st.rerun()

                    st.divider()
        else:
            st.info("No fixtures yet. Label some conversations!")

        # Run tests button
        st.divider()
        if st.button("Run Validation Tests"):
            import subprocess
            result = subprocess.run(
                ["python", "tests/test_theme_extraction.py"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent
            )
            st.code(result.stdout + result.stderr)


if __name__ == "__main__":
    main()
