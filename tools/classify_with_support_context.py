#!/usr/bin/env python3
"""
Conversation context classifier using both customer and support messages.

Leverages support responses to:
1. Disambiguate vague customer messages
2. Confirm issue type and root cause
3. Extract product/feature mentions
4. Identify solutions and related themes
5. Learn support team terminology
"""

import os
import sys
import json
import csv
import re
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from openai import OpenAI


ENHANCED_CLASSIFICATION_PROMPT = """You are analyzing a FULL customer support conversation to understand the conversation type and extract insights.

You have access to:
1. Customer's initial message
2. Support team's response (contains disambiguation, root cause, solutions)
3. Conversation metadata (source type, URL)

**Conversation Details:**
- Source Type: {source_type}
- Source URL: {source_url}
- Subject: {subject}

**Customer Message:**
{customer_message}

**Support Response:**
{support_response}

---

## Your Tasks

### 1. Conversation Type Classification
Classify the primary conversation type (customer's PRIMARY need):
- product_issue (bug, feature not working, data issue)
- how_to_question (feature usage, workflow help)
- feature_request (new capability, enhancement)
- account_issue (login, access, OAuth, permissions)
- billing_question (payment, plan, invoice, subscription)
- configuration_help (setup, integration, settings)
- general_inquiry (unclear intent, exploratory)
- spam (marketing, guest posts, irrelevant)

### 2. Support Knowledge Extraction
Extract insights from the support response:
- **Issue Confirmation**: Did support confirm what the issue is?
- **Root Cause**: Did support explain why it's happening?
- **Product/Feature Mentions**: Specific products, features, or components mentioned
- **Solution Provided**: What fix/workaround was offered?
- **Related Issues**: Any mention of similar/related problems?

### 3. Terminology Learning
Identify precise technical terms used by support team (product names, feature names, technical concepts)

---

Respond in JSON format:
{{
  "conversation_type": "one of the types above",
  "confidence": "high|medium|low",
  "reasoning": "why you chose this type (1-2 sentences)",

  "support_context": {{
    "issue_confirmed": "what support confirmed (or null if not confirmed)",
    "root_cause": "why it's happening (or null)",
    "products_mentioned": ["product1", "product2"],
    "features_mentioned": ["feature1", "feature2"],
    "solution_provided": "what fix was offered (or null)",
    "related_issues": ["similar issue 1", "similar issue 2"]
  }},

  "terminology": ["term1", "term2", "term3"],

  "disambiguation_value": "high|medium|low|none - how much did support response help clarify?",
  "customer_only_classification": "what type would you have guessed from customer message ALONE?"
}}

Focus on extracting actionable insights that improve theme classification and vocabulary."""


def extract_messages(conversation: dict) -> dict:
    """Extract customer and support messages from conversation."""
    result = {
        "customer_message": "",
        "support_message": "",
        "customer_count": 0,
        "support_count": 0
    }

    # Get source body as first customer message
    source_body = conversation.get("source", {}).get("body", "")
    if source_body:
        result["customer_message"] = source_body
        result["customer_count"] = 1

    # Find first admin/teammate response
    parts = conversation.get("conversation_parts", {}).get("conversation_parts", [])

    for part in parts:
        author_type = part.get("author", {}).get("type", "")
        body = part.get("body")

        # Count customer messages
        if author_type == "user" and body:
            result["customer_count"] += 1
            # Use first user message if no source body
            if not result["customer_message"]:
                result["customer_message"] = body

        # Find first support response
        if not result["support_message"] and author_type in ["admin", "teammate"] and body:
            result["support_message"] = body
            result["support_count"] = 1

    # Count remaining support messages
    for part in parts:
        author_type = part.get("author", {}).get("type", "")
        body = part.get("body")
        if author_type in ["admin", "teammate"] and body:
            if body != result["support_message"]:  # Don't double-count first
                result["support_count"] += 1

    return result


def strip_html(html: str) -> str:
    """Remove HTML tags."""
    if not html:
        return ""
    text = re.sub(r"<[^>]+>", " ", html)
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def classify_with_context(client: OpenAI, conversation: dict) -> dict:
    """Classify conversation using full context."""

    # Extract messages
    messages = extract_messages(conversation)

    # Get metadata
    source_type = conversation.get("source", {}).get("type", "unknown")
    source_url = conversation.get("source", {}).get("url", "none")
    subject = conversation.get("source", {}).get("subject", "none")

    # Clean HTML
    customer_msg = strip_html(messages["customer_message"])
    support_msg = strip_html(messages["support_message"])

    # Truncate if very long
    customer_msg = customer_msg[:2000] if customer_msg else "(empty)"
    support_msg = support_msg[:2000] if support_msg else "(no support response yet)"

    # Format prompt
    prompt = ENHANCED_CLASSIFICATION_PROMPT.format(
        source_type=source_type,
        source_url=source_url or "none",
        subject=subject or "none",
        customer_message=customer_msg,
        support_response=support_msg
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a support conversation analyst. Extract maximum value from both customer and support messages. Respond only with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        # Add message metadata
        result["message_metadata"] = {
            "customer_message_count": messages["customer_count"],
            "support_message_count": messages["support_count"],
            "has_support_response": bool(messages["support_message"])
        }

        return result

    except Exception as e:
        print(f"  ⚠️  Classification error: {e}")
        return {
            "conversation_type": "error",
            "confidence": "low",
            "reasoning": str(e),
            "support_context": {},
            "terminology": [],
            "disambiguation_value": "none",
            "message_metadata": {
                "customer_message_count": messages["customer_count"],
                "support_message_count": messages["support_count"],
                "has_support_response": bool(messages["support_message"])
            }
        }


def analyze_support_knowledge(results: list[dict]) -> dict:
    """Extract support knowledge patterns from all conversations."""

    knowledge = {
        "root_causes": Counter(),
        "solutions": Counter(),
        "product_mentions": Counter(),
        "feature_mentions": Counter(),
        "terminology": Counter(),
        "issue_confirmations": Counter()
    }

    for r in results:
        context = r["classification"].get("support_context", {})

        # Root causes
        if context.get("root_cause"):
            knowledge["root_causes"][context["root_cause"]] += 1

        # Solutions
        if context.get("solution_provided"):
            knowledge["solutions"][context["solution_provided"]] += 1

        # Products
        for product in context.get("products_mentioned", []):
            knowledge["product_mentions"][product] += 1

        # Features
        for feature in context.get("features_mentioned", []):
            knowledge["feature_mentions"][feature] += 1

        # Terminology
        for term in r["classification"].get("terminology", []):
            knowledge["terminology"][term] += 1

        # Issue confirmations
        if context.get("issue_confirmed"):
            knowledge["issue_confirmations"][context["issue_confirmed"]] += 1

    return knowledge


def compare_accuracy(results: list[dict]) -> dict:
    """Compare customer-only vs full-conversation classification."""

    comparison = {
        "total": len(results),
        "changed_classification": 0,
        "improved_confidence": 0,
        "high_disambiguation": 0,
        "changes": []
    }

    for r in results:
        classification = r["classification"]

        customer_only = classification.get("customer_only_classification", "")
        full_context = classification.get("conversation_type", "")

        if customer_only and customer_only != full_context:
            comparison["changed_classification"] += 1
            comparison["changes"].append({
                "conversation_id": r["conversation_id"],
                "customer_only": customer_only,
                "full_context": full_context,
                "reasoning": classification.get("reasoning", "")
            })

        # Track disambiguation value
        if classification.get("disambiguation_value") in ["high", "medium"]:
            comparison["high_disambiguation"] += 1

    return comparison


def generate_report(results: list[dict], knowledge: dict, comparison: dict, output_dir: Path):
    """Generate comprehensive analysis report."""

    # 1. CSV output
    csv_path = output_dir / f"context_classification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    csv_headers = [
        "conversation_id", "source_type", "source_url",
        "conversation_type", "confidence", "reasoning",
        "customer_only_type", "changed_from_customer_only",
        "disambiguation_value",
        "has_support_response", "customer_msg_count", "support_msg_count",
        "issue_confirmed", "root_cause", "solution_provided",
        "products_mentioned", "features_mentioned", "terminology"
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=csv_headers)
        writer.writeheader()

        for r in results:
            c = r["classification"]
            ctx = c.get("support_context", {})
            meta = c.get("message_metadata", {})

            writer.writerow({
                "conversation_id": r["conversation_id"],
                "source_type": r["source_type"],
                "source_url": r["source_url"],
                "conversation_type": c.get("conversation_type"),
                "confidence": c.get("confidence"),
                "reasoning": c.get("reasoning", ""),
                "customer_only_type": c.get("customer_only_classification", ""),
                "changed_from_customer_only": c.get("customer_only_classification") != c.get("conversation_type"),
                "disambiguation_value": c.get("disambiguation_value"),
                "has_support_response": meta.get("has_support_response", False),
                "customer_msg_count": meta.get("customer_message_count", 0),
                "support_msg_count": meta.get("support_message_count", 0),
                "issue_confirmed": ctx.get("issue_confirmed", ""),
                "root_cause": ctx.get("root_cause", ""),
                "solution_provided": ctx.get("solution_provided", ""),
                "products_mentioned": "; ".join(ctx.get("products_mentioned", [])),
                "features_mentioned": "; ".join(ctx.get("features_mentioned", [])),
                "terminology": "; ".join(c.get("terminology", []))
            })

    print(f"\n✓ CSV saved to {csv_path}")

    # 2. Support Knowledge Report
    knowledge_report = f"""
{'='*80}
SUPPORT KNOWLEDGE EXTRACTION REPORT
{'='*80}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total Conversations Analyzed: {len(results)}

{'='*80}
TOP ROOT CAUSES (from support responses)
{'='*80}

"""

    for cause, count in knowledge["root_causes"].most_common(10):
        knowledge_report += f"{count:3} | {cause}\n"

    knowledge_report += f"\n{'='*80}\n"
    knowledge_report += "TOP SOLUTIONS PROVIDED\n"
    knowledge_report += f"{'='*80}\n\n"

    for solution, count in knowledge["solutions"].most_common(10):
        knowledge_report += f"{count:3} | {solution}\n"

    knowledge_report += f"\n{'='*80}\n"
    knowledge_report += "PRODUCT MENTIONS (by support team)\n"
    knowledge_report += f"{'='*80}\n\n"

    for product, count in knowledge["product_mentions"].most_common(15):
        knowledge_report += f"{count:3} | {product}\n"

    knowledge_report += f"\n{'='*80}\n"
    knowledge_report += "FEATURE MENTIONS (by support team)\n"
    knowledge_report += f"{'='*80}\n\n"

    for feature, count in knowledge["feature_mentions"].most_common(15):
        knowledge_report += f"{count:3} | {feature}\n"

    knowledge_report += f"\n{'='*80}\n"
    knowledge_report += "SUPPORT TERMINOLOGY (for vocabulary enhancement)\n"
    knowledge_report += f"{'='*80}\n\n"

    for term, count in knowledge["terminology"].most_common(20):
        knowledge_report += f"{count:3} | {term}\n"

    # 3. Accuracy Comparison Report
    accuracy_report = f"""

{'='*80}
ACCURACY COMPARISON: Customer-Only vs Full-Context
{'='*80}

Total Conversations: {comparison['total']}
Changed Classification: {comparison['changed_classification']} ({100*comparison['changed_classification']/comparison['total']:.1f}%)
High Disambiguation Value: {comparison['high_disambiguation']} ({100*comparison['high_disambiguation']/comparison['total']:.1f}%)

"""

    if comparison['changes']:
        accuracy_report += f"\n{'='*80}\n"
        accuracy_report += "CLASSIFICATION CHANGES\n"
        accuracy_report += f"{'='*80}\n\n"

        for change in comparison['changes'][:10]:  # Show first 10
            accuracy_report += f"Conversation: {change['conversation_id']}\n"
            accuracy_report += f"  Customer-Only: {change['customer_only']}\n"
            accuracy_report += f"  Full Context:  {change['full_context']}\n"
            accuracy_report += f"  Why: {change['reasoning']}\n\n"

    # Combine reports
    full_report = knowledge_report + accuracy_report

    print(full_report)

    # Save to file
    report_path = output_dir / f"context_analysis_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_path.write_text(full_report)
    print(f"✓ Report saved to {report_path}")

    # 4. Save knowledge as JSON for vocabulary enrichment
    knowledge_path = output_dir / f"support_knowledge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(knowledge_path, 'w') as f:
        json.dump({
            "root_causes": dict(knowledge["root_causes"].most_common(50)),
            "solutions": dict(knowledge["solutions"].most_common(50)),
            "products": dict(knowledge["product_mentions"].most_common(50)),
            "features": dict(knowledge["feature_mentions"].most_common(50)),
            "terminology": dict(knowledge["terminology"].most_common(100)),
            "issue_confirmations": dict(knowledge["issue_confirmations"].most_common(50))
        }, f, indent=2)
    print(f"✓ Knowledge base saved to {knowledge_path}")

    # 5. Save full results
    results_path = output_dir / f"context_classification_full_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_path, 'w') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total": len(results),
            "comparison": comparison,
            "results": results
        }, f, indent=2)
    print(f"✓ Full results saved to {results_path}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Classify conversations with support context")
    parser.add_argument("--input", type=str, required=True, help="JSON file with conversation data")
    parser.add_argument("--output-dir", type=str, default="data/conversation_types",
                       help="Output directory for results")
    args = parser.parse_args()

    # Load conversations
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Input file not found: {input_path}")
        return 1

    with open(input_path) as f:
        conversations = json.load(f)

    print(f"\n✓ Loaded {len(conversations)} conversations from {input_path}")

    # Initialize OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Classify with context
    print(f"\nClassifying with full conversation context...")
    results = []

    for i, conv in enumerate(conversations, 1):
        conv_id = conv.get("id", "unknown")
        print(f"[{i}/{len(conversations)}] Classifying {conv_id}...", end=" ")

        classification = classify_with_context(client, conv)

        result = {
            "conversation_id": conv_id,
            "created_at": conv.get("created_at"),
            "source_type": conv.get("source", {}).get("type", "unknown"),
            "source_url": conv.get("source", {}).get("url", ""),
            "classification": classification
        }

        results.append(result)
        print(f"→ {classification['conversation_type']} ({classification['confidence']}) | Disambiguation: {classification.get('disambiguation_value', 'none')}")

    # Extract support knowledge
    print(f"\nExtracting support knowledge patterns...")
    knowledge = analyze_support_knowledge(results)

    # Compare accuracy
    print(f"\nComparing customer-only vs full-context...")
    comparison = compare_accuracy(results)

    # Generate reports
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generate_report(results, knowledge, comparison, output_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
