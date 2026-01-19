#!/usr/bin/env python3
"""
VDD Codebase Search - Autonomous Learning Phase

Analyzes evaluation results and generates code changes to improve search quality.
This script is the "brain" of the autonomous VDD loop, using Claude to:

1. Diagnose WHY search is failing (missed files, wrong patterns, bad keywords)
2. Generate SPECIFIC code changes to codebase_context_provider.py
3. Apply changes safely with rollback capability
4. Track learnings for future iterations

Architecture:
- Reads evaluation results JSON (output of evaluate_results_v2.py)
- Analyzes precision/recall failures per product area
- Uses Claude to propose targeted code fixes
- Applies fixes to the search logic
- Outputs a learning summary for the next iteration

Usage:
    python apply_learnings.py < evaluation.json > learning_summary.json

    # Or with explicit paths
    python apply_learnings.py --input evaluation.json --output learnings.json
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
SEARCH_PROVIDER_PATH = PROJECT_ROOT / "src" / "story_tracking" / "services" / "codebase_context_provider.py"
BACKUP_DIR = SCRIPT_DIR / "backups"
LEARNINGS_PATH = SCRIPT_DIR / "learned_patterns.json"
CONFIG_PATH = SCRIPT_DIR / "config.json"

# Load config
if not CONFIG_PATH.exists():
    print(f"ERROR: Config file not found: {CONFIG_PATH}", file=sys.stderr)
    print("Copy config.json.example to config.json and configure settings", file=sys.stderr)
    sys.exit(1)

with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

# Validate required config keys
_required_keys = ["models"]
for _key in _required_keys:
    if _key not in CONFIG:
        print(f"ERROR: Missing required config key: {_key}", file=sys.stderr)
        sys.exit(1)

if "judge" not in CONFIG.get("models", {}):
    print("ERROR: Missing required config key: models.judge", file=sys.stderr)
    sys.exit(1)

# Valid model names (for command injection prevention)
VALID_MODELS = frozenset(CONFIG["models"].values())


def validate_model(model: str) -> str:
    """Validate model string against known safe values to prevent command injection."""
    if model not in VALID_MODELS:
        raise ValueError(f"Invalid model: {model}. Must be one of {VALID_MODELS}")
    return model


def load_search_provider_code() -> str:
    """Load the current codebase_context_provider.py source code."""
    if not SEARCH_PROVIDER_PATH.exists():
        raise FileNotFoundError(f"Search provider not found: {SEARCH_PROVIDER_PATH}")
    return SEARCH_PROVIDER_PATH.read_text()


def backup_search_provider(iteration: int) -> Path:
    """Create a backup of the search provider before modifications."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"codebase_context_provider_iter{iteration}_{timestamp}.py"
    shutil.copy(SEARCH_PROVIDER_PATH, backup_path)
    print(f"  Backed up to: {backup_path}", file=sys.stderr)
    return backup_path


def analyze_failures(evaluation: dict) -> dict:
    """
    Analyze evaluation results to identify failure patterns.

    Returns a structured analysis of:
    - Files we missed (false negatives - hurt recall)
    - Files we found that weren't relevant (false positives - hurt precision)
    - Patterns in the failures (by product area, file type, etc.)
    """
    conversations = evaluation.get("conversations", [])

    # Aggregate failure patterns
    missed_files = []  # Files in ground truth we didn't find
    wrong_files = []   # Files we found that weren't relevant
    by_product_area = {}

    for conv in conversations:
        conv_id = conv.get("conversation_id", "unknown")
        product_area = conv.get("product_area", "uncertain")
        analysis = conv.get("ground_truth_analysis", {})

        if product_area not in by_product_area:
            by_product_area[product_area] = {
                "missed": [],
                "wrong": [],
                "precision_sum": 0,
                "recall_sum": 0,
                "count": 0
            }

        area_stats = by_product_area[product_area]
        area_stats["count"] += 1
        area_stats["precision_sum"] += analysis.get("precision", 0)
        area_stats["recall_sum"] += analysis.get("recall", 0)

        # Collect missed files (ground truth unique = files we should have found)
        gt_unique = analysis.get("ground_truth_unique", [])
        for f in gt_unique:
            missed_files.append({
                "file": f,
                "conversation_id": conv_id,
                "product_area": product_area,
                "issue_summary": conv.get("issue_summary", "")[:200]
            })
            area_stats["missed"].append(f)

        # Collect wrong files (our unique that judge said weren't relevant)
        judgments = analysis.get("judgments", [])
        for j in judgments:
            if not j.get("is_relevant", True):
                wrong_files.append({
                    "file": j.get("file_ref", ""),
                    "conversation_id": conv_id,
                    "product_area": product_area,
                    "reason": j.get("reasoning", "")
                })
                area_stats["wrong"].append(j.get("file_ref", ""))

    # Calculate averages
    for area, stats in by_product_area.items():
        if stats["count"] > 0:
            stats["avg_precision"] = stats["precision_sum"] / stats["count"]
            stats["avg_recall"] = stats["recall_sum"] / stats["count"]

    return {
        "missed_files": missed_files,
        "wrong_files": wrong_files,
        "by_product_area": by_product_area,
        "total_conversations": len(conversations),
        "aggregate_precision": evaluation.get("aggregate", {}).get("precision", 0),
        "aggregate_recall": evaluation.get("aggregate", {}).get("recall", 0)
    }


def generate_improvement_proposal(
    analysis: dict,
    current_code: str,
    iteration: int
) -> dict:
    """
    Use Claude to analyze failures and propose code improvements.

    Returns a structured proposal with:
    - diagnosis: What's causing the failures
    - changes: List of specific code changes to make
    - expected_impact: Predicted improvement in precision/recall
    """
    # Build the prompt with failure context
    missed_summary = []
    for m in analysis["missed_files"][:20]:  # Limit to top 20
        missed_summary.append(
            f"- {m['file']} (area: {m['product_area']}, issue: {m['issue_summary'][:100]}...)"
        )

    wrong_summary = []
    for w in analysis["wrong_files"][:20]:
        wrong_summary.append(
            f"- {w['file']} (area: {w['product_area']}, reason: {w['reason'][:100]}...)"
        )

    area_stats = []
    for area, stats in analysis["by_product_area"].items():
        area_stats.append(
            f"- {area}: precision={stats.get('avg_precision', 0):.2f}, "
            f"recall={stats.get('avg_recall', 0):.2f}, "
            f"missed={len(stats['missed'])}, wrong={len(stats['wrong'])}"
        )

    prompt = f"""You are an expert at improving codebase search algorithms. Analyze these search failures and propose specific code changes.

## Current Metrics
- Overall Precision: {analysis['aggregate_precision']:.2f}
- Overall Recall: {analysis['aggregate_recall']:.2f}
- Target: Precision >= 0.8, Recall >= 0.7

## Per-Product-Area Performance
{chr(10).join(area_stats)}

## Files We MISSED (Hurt Recall - These should have been found)
{chr(10).join(missed_summary) if missed_summary else "None"}

## Files We Wrongly Included (Hurt Precision - These weren't relevant)
{chr(10).join(wrong_summary) if wrong_summary else "None"}

## Current Search Logic (codebase_context_provider.py)

```python
{current_code}
```

## Your Task

Analyze the failures and propose SPECIFIC, TARGETED code changes. Focus on:

1. **Pattern Analysis**: What patterns do the missed files have in common?
   - Are they in directories we're not searching?
   - Do they use naming conventions we're missing?
   - Are there keywords we should be extracting?

2. **False Positive Analysis**: Why did we find irrelevant files?
   - Are our patterns too broad?
   - Are we matching common words that aren't specific?

3. **Product Area Focus**: Which areas need the most improvement?

## Output Format

Respond with a JSON object:
```json
{{
    "diagnosis": "Brief explanation of the main issues",
    "changes": [
        {{
            "type": "add_pattern|modify_pattern|add_keyword|modify_function",
            "location": "function name or line range",
            "description": "What this change does",
            "old_code": "exact code to find (for modifications)",
            "new_code": "replacement code",
            "expected_impact": "which metric this improves and by how much"
        }}
    ],
    "expected_precision_delta": 0.05,
    "expected_recall_delta": 0.10,
    "confidence": "HIGH|MEDIUM|LOW",
    "reasoning": "Why these changes should help"
}}
```

## Constraints

1. Make MINIMAL changes - target the biggest impact with smallest change
2. Don't break existing functionality - changes should be additive or targeted replacements
3. Each change should be independently testable
4. Prefer adding new patterns over modifying existing ones (lower risk)
5. Maximum 3 changes per iteration to maintain stability
6. This is iteration {iteration} - be conservative early, more aggressive later

Focus on the MOST IMPACTFUL changes first. If precision is low, prioritize filtering. If recall is low, prioritize new patterns.
"""

    # Use Claude CLI instead of SDK to avoid API credit usage
    # Validate model to prevent command injection
    model = validate_model(CONFIG["models"]["judge"])

    # Build claude command - use interactive mode via stdin (subscription, not API credits)
    cmd = [
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
    ]

    try:
        # Run claude CLI with timeout, passing prompt via stdin
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for analysis
        )

        response_text = result.stdout + result.stderr

        # Log if command failed
        if result.returncode != 0:
            print(f"  Warning: Claude CLI returned exit code {result.returncode}", file=sys.stderr)
            if "Credit balance" in response_text:
                print("  Note: If you see credit errors, ensure ANTHROPIC_API_KEY is unset", file=sys.stderr)

    except subprocess.TimeoutExpired:
        print("  Error: Claude CLI timed out", file=sys.stderr)
        return {
            "diagnosis": "Analysis timed out",
            "changes": [],
            "expected_precision_delta": 0,
            "expected_recall_delta": 0,
            "confidence": "LOW",
            "reasoning": "Claude CLI timed out after 5 minutes"
        }
    except Exception as e:
        print(f"  Error running Claude CLI: {e}", file=sys.stderr)
        return {
            "diagnosis": f"CLI error: {e}",
            "changes": [],
            "expected_precision_delta": 0,
            "expected_recall_delta": 0,
            "confidence": "LOW",
            "reasoning": str(e)
        }

    # Extract JSON from response using brace-counting (greedy regex is unsafe)
    # Look for JSON object starting with expected keys
    json_start = -1
    for key in ['"diagnosis"', '"changes"', '"expected_precision_delta"']:
        idx = response_text.find(key)
        if idx != -1:
            # Find the opening brace before this key
            start = response_text.rfind('{', max(0, idx - 100), idx)
            if start != -1:
                json_start = start
                break

    if json_start != -1:
        # Use brace counting to find matching close brace
        brace_count = 0
        json_end = -1
        for i, c in enumerate(response_text[json_start:json_start + 10000]):
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = json_start + i + 1
                    break
        if json_end != -1:
            try:
                return json.loads(response_text[json_start:json_end])
            except json.JSONDecodeError:
                pass

    # Fallback if JSON parsing fails
    return {
        "diagnosis": "Could not parse proposal",
        "changes": [],
        "expected_precision_delta": 0,
        "expected_recall_delta": 0,
        "confidence": "LOW",
        "reasoning": response_text[:500] if response_text else "No response from Claude CLI"
    }


def apply_code_changes(proposal: dict, current_code: str) -> tuple[str, list[dict]]:
    """
    Apply proposed code changes to the search provider.

    Returns:
    - Modified code string
    - List of applied changes with status
    """
    modified_code = current_code
    applied_changes = []

    for change in proposal.get("changes", []):
        change_type = change.get("type", "")
        old_code = change.get("old_code", "")
        new_code = change.get("new_code", "")
        description = change.get("description", "")

        if not new_code:
            applied_changes.append({
                **change,
                "status": "skipped",
                "reason": "No new code provided"
            })
            continue

        if change_type in ["modify_pattern", "modify_function"] and old_code:
            # Replace existing code
            if old_code in modified_code:
                modified_code = modified_code.replace(old_code, new_code, 1)
                applied_changes.append({
                    **change,
                    "status": "applied",
                    "reason": "Successfully replaced code"
                })
            else:
                applied_changes.append({
                    **change,
                    "status": "failed",
                    "reason": "Old code not found in source"
                })

        elif change_type in ["add_pattern", "add_keyword"]:
            # Find insertion point based on location hint
            location = change.get("location", "")

            # Try to find the function to modify
            if location:
                func_match = re.search(
                    rf'(def {re.escape(location)}\([^)]*\)[^:]*:.*?)(\n    def |\nclass |\Z)',
                    modified_code,
                    re.DOTALL
                )
                if func_match:
                    # Insert at end of function (before return or last line)
                    func_body = func_match.group(1)

                    # Find the return statement or end of function
                    return_match = re.search(r'\n        return ', func_body)
                    if return_match:
                        insert_pos = func_match.start() + return_match.start()
                        modified_code = (
                            modified_code[:insert_pos] +
                            f"\n        # Added by VDD iteration\n        {new_code}\n" +
                            modified_code[insert_pos:]
                        )
                        applied_changes.append({
                            **change,
                            "status": "applied",
                            "reason": f"Inserted in function {location}"
                        })
                    else:
                        applied_changes.append({
                            **change,
                            "status": "failed",
                            "reason": "Could not find insertion point in function"
                        })
                else:
                    applied_changes.append({
                        **change,
                        "status": "failed",
                        "reason": f"Function {location} not found"
                    })
            else:
                applied_changes.append({
                    **change,
                    "status": "skipped",
                    "reason": "No location specified for addition"
                })
        else:
            applied_changes.append({
                **change,
                "status": "skipped",
                "reason": f"Unknown change type: {change_type}"
            })

    return modified_code, applied_changes


def save_learnings(
    analysis: dict,
    proposal: dict,
    applied_changes: list[dict],
    iteration: int
) -> None:
    """Save learnings to the knowledge cache for future iterations."""
    # Load existing learnings
    if LEARNINGS_PATH.exists():
        with open(LEARNINGS_PATH) as f:
            learnings = json.load(f)
    else:
        learnings = {
            "version": "1.0",
            "iterations": [],
            "patterns_tried": [],
            "patterns_effective": []
        }

    # Add this iteration's learnings
    iteration_record = {
        "iteration": iteration,
        "timestamp": datetime.utcnow().isoformat(),
        "metrics_before": {
            "precision": analysis["aggregate_precision"],
            "recall": analysis["aggregate_recall"]
        },
        "diagnosis": proposal.get("diagnosis", ""),
        "changes_attempted": len(proposal.get("changes", [])),
        "changes_applied": len([c for c in applied_changes if c.get("status") == "applied"]),
        "expected_impact": {
            "precision_delta": proposal.get("expected_precision_delta", 0),
            "recall_delta": proposal.get("expected_recall_delta", 0)
        }
    }

    learnings["iterations"].append(iteration_record)

    # Track patterns for future reference
    for change in proposal.get("changes", []):
        learnings["patterns_tried"].append({
            "iteration": iteration,
            "description": change.get("description", ""),
            "status": next(
                (c.get("status") for c in applied_changes
                 if c.get("description") == change.get("description")),
                "unknown"
            )
        })

    # Save
    with open(LEARNINGS_PATH, "w") as f:
        json.dump(learnings, f, indent=2)

    print(f"  Saved learnings to: {LEARNINGS_PATH}", file=sys.stderr)


def run_learning_phase(evaluation: dict, dry_run: bool = False) -> dict:
    """
    Run the complete autonomous learning phase.

    Args:
        evaluation: Output from evaluate_results_v2.py
        dry_run: If True, don't actually modify files

    Returns:
        Learning summary with changes made and expected impact
    """
    iteration = evaluation.get("iteration_number", 1)

    print(f"\n=== VDD Learning Phase (Iteration {iteration}) ===", file=sys.stderr)

    # Step 1: Analyze failures
    print("\n[1/5] Analyzing evaluation failures...", file=sys.stderr)
    analysis = analyze_failures(evaluation)

    print(f"  Aggregate: precision={analysis['aggregate_precision']:.2f}, "
          f"recall={analysis['aggregate_recall']:.2f}", file=sys.stderr)
    print(f"  Files missed: {len(analysis['missed_files'])}", file=sys.stderr)
    print(f"  Files wrong: {len(analysis['wrong_files'])}", file=sys.stderr)

    # Step 2: Load current search code
    print("\n[2/5] Loading current search provider...", file=sys.stderr)
    current_code = load_search_provider_code()
    print(f"  Loaded {len(current_code)} bytes", file=sys.stderr)

    # Step 3: Generate improvement proposal
    print("\n[3/5] Generating improvement proposal (using Claude)...", file=sys.stderr)
    proposal = generate_improvement_proposal(analysis, current_code, iteration)

    print(f"  Diagnosis: {proposal.get('diagnosis', 'N/A')[:100]}...", file=sys.stderr)
    print(f"  Proposed changes: {len(proposal.get('changes', []))}", file=sys.stderr)
    print(f"  Confidence: {proposal.get('confidence', 'N/A')}", file=sys.stderr)

    # Step 4: Apply changes (unless dry run)
    applied_changes = []

    if proposal.get("changes") and not dry_run:
        print("\n[4/5] Applying code changes...", file=sys.stderr)

        # Backup first
        backup_path = backup_search_provider(iteration)

        # Apply changes
        modified_code, applied_changes = apply_code_changes(proposal, current_code)

        # Count successful applications
        successful = [c for c in applied_changes if c.get("status") == "applied"]
        failed = [c for c in applied_changes if c.get("status") == "failed"]

        print(f"  Applied: {len(successful)}", file=sys.stderr)
        print(f"  Failed: {len(failed)}", file=sys.stderr)

        if successful:
            # Write modified code
            SEARCH_PROVIDER_PATH.write_text(modified_code)
            print(f"  Updated: {SEARCH_PROVIDER_PATH}", file=sys.stderr)

            for change in successful:
                print(f"    ✓ {change.get('description', 'N/A')[:60]}...", file=sys.stderr)

        if failed:
            for change in failed:
                print(f"    ✗ {change.get('description', 'N/A')[:40]}... "
                      f"({change.get('reason', '')})", file=sys.stderr)

    elif dry_run:
        print("\n[4/5] Dry run - skipping code changes", file=sys.stderr)
        for change in proposal.get("changes", []):
            print(f"  Would apply: {change.get('description', 'N/A')[:60]}...", file=sys.stderr)
    else:
        print("\n[4/5] No changes proposed", file=sys.stderr)

    # Step 5: Save learnings
    print("\n[5/5] Saving learnings...", file=sys.stderr)
    save_learnings(analysis, proposal, applied_changes, iteration)

    # Build summary output
    summary = {
        "iteration": iteration,
        "timestamp": datetime.utcnow().isoformat(),
        "metrics_before": {
            "precision": analysis["aggregate_precision"],
            "recall": analysis["aggregate_recall"]
        },
        "analysis": {
            "files_missed": len(analysis["missed_files"]),
            "files_wrong": len(analysis["wrong_files"]),
            "by_product_area": {
                area: {
                    "precision": stats.get("avg_precision", 0),
                    "recall": stats.get("avg_recall", 0)
                }
                for area, stats in analysis["by_product_area"].items()
            }
        },
        "proposal": {
            "diagnosis": proposal.get("diagnosis", ""),
            "changes_proposed": len(proposal.get("changes", [])),
            "expected_precision_delta": proposal.get("expected_precision_delta", 0),
            "expected_recall_delta": proposal.get("expected_recall_delta", 0),
            "confidence": proposal.get("confidence", "LOW")
        },
        "application": {
            "dry_run": dry_run,
            "changes_applied": len([c for c in applied_changes if c.get("status") == "applied"]),
            "changes_failed": len([c for c in applied_changes if c.get("status") == "failed"]),
            "details": applied_changes
        }
    }

    print(f"\n=== Learning Phase Complete ===", file=sys.stderr)
    print(f"  Changes applied: {summary['application']['changes_applied']}", file=sys.stderr)
    print(f"  Expected precision delta: +{proposal.get('expected_precision_delta', 0):.2f}", file=sys.stderr)
    print(f"  Expected recall delta: +{proposal.get('expected_recall_delta', 0):.2f}", file=sys.stderr)

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="VDD Codebase Search - Autonomous Learning Phase"
    )
    parser.add_argument("--input", "-i", type=Path,
                       help="Path to evaluation results JSON (default: stdin)")
    parser.add_argument("--output", "-o", type=Path,
                       help="Path to write learning summary (default: stdout)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Analyze and propose changes but don't apply them")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Verbose output")

    args = parser.parse_args()

    # Load evaluation results
    if args.input:
        with open(args.input) as f:
            evaluation = json.load(f)
    else:
        evaluation = json.load(sys.stdin)

    # Run learning phase
    summary = run_learning_phase(evaluation, dry_run=args.dry_run)

    # Output summary
    if args.output:
        with open(args.output, "w") as f:
            json.dump(summary, f, indent=2)
    else:
        json.dump(summary, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
