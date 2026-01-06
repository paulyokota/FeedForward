"""
Conversation Labeling UI

Run with: streamlit run tools/labeler.py
"""

import json
import re
import streamlit as st
from pathlib import Path
from datetime import datetime

# Paths
DATA_DIR = Path(__file__).parent.parent / "data"
SAMPLES_DIR = DATA_DIR / "samples"
FIXTURES_FILE = DATA_DIR / "labeled_fixtures.json"
SKIPPED_FILE = DATA_DIR / "skipped_conversations.json"

# Template texts to filter out
TEMPLATE_TEXTS = [
    'i have a product question or feedback',
    'hi', 'hello', 'help', 'hey'
]

# Classification categories (from schema analysis)
ISSUE_TYPES = [
    "bug_report",
    "feature_request",
    "product_question",   # How do I use feature X?
    "plan_question",      # What's included in my plan?
    "marketing_question", # How do I grow my audience?
    "billing",
    "account_access",
    "feedback",
    "other",
]

# Churn risk is a separate flag (stacks with any issue type)

SENTIMENTS = ["frustrated", "neutral", "satisfied"]

PRIORITIES = ["urgent", "high", "normal", "low"]


def strip_html(html: str) -> str:
    """Remove HTML tags and normalize whitespace."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_quality_conversation(conv: dict) -> tuple[bool, str]:
    """Check if conversation is good for labeling. Returns (is_good, reason)."""
    src = conv.get("source", {})
    delivered_as = src.get("delivered_as", "unknown")
    author_type = src.get("author", {}).get("type", "unknown")
    body = strip_html(src.get("body", ""))

    if delivered_as != "customer_initiated":
        return False, f"outbound ({delivered_as})"
    if author_type != "user":
        return False, f"author is {author_type}"
    if len(body) < 20:
        return False, "too short"
    if body.lower().strip() in TEMPLATE_TEXTS:
        return False, "template text"
    return True, "ok"


def load_conversations() -> list[dict]:
    """Load all sample conversations."""
    conversations = []

    # Load from multiple sample files
    sample_files = [
        SAMPLES_DIR / "intercom_filtered.json",
        SAMPLES_DIR / "intercom_diverse.json",
    ]

    seen_ids = set()
    for sample_file in sample_files:
        if not sample_file.exists():
            continue
        with open(sample_file) as f:
            data = json.load(f)
            for conv in data.get("conversations", []):
                if conv["id"] in seen_ids:
                    continue
                seen_ids.add(conv["id"])
                is_good, reason = is_quality_conversation(conv)
                conversations.append(
                    {
                        "id": conv["id"],
                        "source_type": conv.get("source", {}).get("type", "unknown"),
                        "subject": strip_html(
                            conv.get("source", {}).get("subject", "")
                        ),
                        "body": strip_html(conv.get("source", {}).get("body", "")),
                        "author_name": conv.get("source", {})
                        .get("author", {})
                        .get("name", "Unknown"),
                        "author_email": conv.get("source", {})
                        .get("author", {})
                        .get("email", ""),
                        "state": conv.get("state", "unknown"),
                        "priority": conv.get("priority", "not_priority"),
                        "topics": [
                            t.get("name")
                            for t in conv.get("topics", {}).get("topics", [])
                        ],
                        "ai_participated": conv.get("ai_agent_participated", False),
                        "has_parts": False,
                        "is_quality": is_good,
                        "quality_reason": reason,
                    }
                )

    # Load full conversations with parts
    for conv_file in SAMPLES_DIR.glob("conv_*.json"):
        with open(conv_file) as f:
            conv = json.load(f)
            # Check if already loaded (by id)
            if any(c["id"] == conv["id"] for c in conversations):
                # Update with full parts
                for c in conversations:
                    if c["id"] == conv["id"]:
                        parts = conv.get("conversation_parts", {}).get(
                            "conversation_parts", []
                        )
                        c["parts"] = [
                            {
                                "author_type": p.get("author", {}).get(
                                    "type", "unknown"
                                ),
                                "author_name": p.get("author", {}).get(
                                    "name", "Unknown"
                                ),
                                "body": strip_html(p.get("body", "")),
                                "part_type": p.get("part_type", "unknown"),
                            }
                            for p in parts
                            if p.get("body")
                        ]
                        c["has_parts"] = True
            else:
                # Add new conversation
                parts = conv.get("conversation_parts", {}).get("conversation_parts", [])
                conversations.append(
                    {
                        "id": conv["id"],
                        "source_type": conv.get("source", {}).get("type", "unknown"),
                        "subject": strip_html(
                            conv.get("source", {}).get("subject", "")
                        ),
                        "body": strip_html(conv.get("source", {}).get("body", "")),
                        "author_name": conv.get("source", {})
                        .get("author", {})
                        .get("name", "Unknown"),
                        "author_email": conv.get("source", {})
                        .get("author", {})
                        .get("email", ""),
                        "state": conv.get("state", "unknown"),
                        "priority": conv.get("priority", "not_priority"),
                        "topics": [
                            t.get("name")
                            for t in conv.get("topics", {}).get("topics", [])
                        ],
                        "ai_participated": conv.get("ai_agent_participated", False),
                        "has_parts": True,
                        "parts": [
                            {
                                "author_type": p.get("author", {}).get(
                                    "type", "unknown"
                                ),
                                "author_name": p.get("author", {}).get(
                                    "name", "Unknown"
                                ),
                                "body": strip_html(p.get("body", "")),
                                "part_type": p.get("part_type", "unknown"),
                            }
                            for p in parts
                            if p.get("body")
                        ],
                    }
                )

    return conversations


def load_labels() -> dict:
    """Load existing labels."""
    if FIXTURES_FILE.exists():
        with open(FIXTURES_FILE) as f:
            return json.load(f)
    return {"labeled": [], "metadata": {"created": datetime.now().isoformat()}}


def save_labels(labels: dict):
    """Save labels to file."""
    FIXTURES_FILE.parent.mkdir(parents=True, exist_ok=True)
    labels["metadata"]["updated"] = datetime.now().isoformat()
    with open(FIXTURES_FILE, "w") as f:
        json.dump(labels, f, indent=2)


def main():
    st.set_page_config(page_title="FeedForward Labeler", layout="wide")
    st.title("FeedForward Conversation Labeler")

    # Load data
    conversations = load_conversations()
    labels_data = load_labels()
    labeled_ids = {item["id"] for item in labels_data.get("labeled", [])}

    # Sidebar stats
    st.sidebar.header("Progress")
    st.sidebar.metric("Total Conversations", len(conversations))
    st.sidebar.metric("Labeled", len(labeled_ids))
    st.sidebar.metric("Remaining", len(conversations) - len(labeled_ids))

    if st.sidebar.button("Export Labels"):
        st.sidebar.download_button(
            "Download JSON",
            json.dumps(labels_data, indent=2),
            "labeled_fixtures.json",
            "application/json",
        )

    # Load skipped IDs
    skipped_ids = set()
    if SKIPPED_FILE.exists():
        with open(SKIPPED_FILE) as f:
            skipped_ids = set(json.load(f).get("skipped", []))

    # Filter options
    st.sidebar.header("Filter")
    show_labeled = st.sidebar.checkbox("Show already labeled", value=False)
    show_skipped = st.sidebar.checkbox("Show skipped/bad", value=False)
    filter_type = st.sidebar.selectbox(
        "Source type", ["all", "conversation", "email"]
    )

    # Quality stats
    quality_count = sum(1 for c in conversations if c.get("is_quality", True))
    st.sidebar.caption(f"Quality samples: {quality_count}/{len(conversations)}")
    st.sidebar.caption(f"Skipped: {len(skipped_ids)}")

    # Filter conversations
    filtered = conversations
    if not show_labeled:
        filtered = [c for c in filtered if c["id"] not in labeled_ids]
    if not show_skipped:
        filtered = [c for c in filtered if c["id"] not in skipped_ids]
    if filter_type != "all":
        filtered = [c for c in filtered if c["source_type"] == filter_type]

    if not filtered:
        st.success("All conversations labeled!")
        return

    # Conversation selector
    conv_options = {f"{c['id'][:15]}... - {c['body'][:50]}": c["id"] for c in filtered}
    selected_label = st.selectbox("Select conversation", list(conv_options.keys()))
    selected_id = conv_options[selected_label]
    conv = next(c for c in conversations if c["id"] == selected_id)

    # Display conversation
    st.divider()
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Conversation")

        # Metadata
        meta_cols = st.columns(4)
        meta_cols[0].caption(f"Source: {conv['source_type']}")
        meta_cols[1].caption(f"State: {conv['state']}")
        meta_cols[2].caption(f"AI: {'Yes' if conv['ai_participated'] else 'No'}")
        meta_cols[3].caption(f"Topics: {', '.join(conv['topics']) or 'None'}")

        # Initial message
        st.markdown(f"**From:** {conv['author_name']} ({conv['author_email']})")
        if conv["subject"]:
            st.markdown(f"**Subject:** {conv['subject']}")
        st.info(conv["body"])

        # Conversation parts (if available)
        if conv.get("parts"):
            st.markdown("**Thread:**")
            for part in conv["parts"]:
                if part["body"] and len(part["body"]) > 10:
                    author_type = part["author_type"]
                    icon = "🤖" if author_type == "bot" else "👤" if author_type == "user" else "👨‍💼"
                    with st.expander(f"{icon} {part['author_name']}", expanded=False):
                        st.write(part["body"])

    with col2:
        st.subheader("Labels")

        # Get existing labels for this conversation
        existing = next(
            (item for item in labels_data["labeled"] if item["id"] == selected_id),
            None,
        )

        # Classification inputs (use conversation ID as key to reset on new selection)
        issue_type = st.selectbox(
            "Issue Type",
            ISSUE_TYPES,
            index=ISSUE_TYPES.index(existing["issue_type"]) if existing else 0,
            key=f"issue_{selected_id}",
        )

        sentiment = st.selectbox(
            "Sentiment",
            SENTIMENTS,
            index=SENTIMENTS.index(existing["sentiment"]) if existing else 1,
            key=f"sentiment_{selected_id}",
        )

        priority = st.selectbox(
            "Priority",
            PRIORITIES,
            index=PRIORITIES.index(existing["priority"]) if existing else 2,
            key=f"priority_{selected_id}",
        )

        churn_risk = st.checkbox(
            "🚨 Churn Risk",
            value=existing.get("churn_risk", False) if existing else False,
            key=f"churn_{selected_id}",
            help="Customer showing signs of leaving (cancellation, frustration, switching)",
        )

        product_area = st.text_input(
            "Product Area (optional)",
            value=existing.get("product_area", "") if existing else "",
            placeholder="e.g., scheduling, billing, pinterest",
            key=f"product_{selected_id}",
        )

        notes = st.text_area(
            "Notes (optional)",
            value=existing.get("notes", "") if existing else "",
            placeholder="Any additional context...",
            key=f"notes_{selected_id}",
        )

        # Save button
        if st.button("Save Label", type="primary", use_container_width=True):
            label_entry = {
                "id": selected_id,
                "issue_type": issue_type,
                "sentiment": sentiment,
                "priority": priority,
                "churn_risk": churn_risk,
                "product_area": product_area if product_area else None,
                "notes": notes if notes else None,
                "input_text": conv["body"],
                "labeled_at": datetime.now().isoformat(),
            }

            # Update or add
            if existing:
                labels_data["labeled"] = [
                    item if item["id"] != selected_id else label_entry
                    for item in labels_data["labeled"]
                ]
            else:
                labels_data["labeled"].append(label_entry)

            save_labels(labels_data)
            st.success("Saved!")
            st.rerun()

        # Skip button
        if st.button("Skip", use_container_width=True):
            st.rerun()

        st.divider()

        # Mark as bad sample button
        if st.button("❌ Mark as Bad Sample", use_container_width=True, type="secondary"):
            # Load existing skipped
            skipped_data = {"skipped": []}
            if SKIPPED_FILE.exists():
                with open(SKIPPED_FILE) as f:
                    skipped_data = json.load(f)

            if selected_id not in skipped_data["skipped"]:
                skipped_data["skipped"].append(selected_id)
                with open(SKIPPED_FILE, "w") as f:
                    json.dump(skipped_data, f, indent=2)
                st.warning("Marked as bad sample")
                st.rerun()


if __name__ == "__main__":
    main()
