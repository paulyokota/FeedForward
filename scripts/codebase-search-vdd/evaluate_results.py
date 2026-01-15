#!/usr/bin/env python3
"""
Codebase Search VDD - Dual Exploration Evaluator

Orchestrates the dual exploration evaluation process:
1. Launch two independent Claude Code explorations (Opus + Sonnet during calibration)
2. Construct ground truth from union of files found by both runs
3. Compare our search results against ground truth
4. Judge "Our Unique" files for relevance using judge model
5. Calculate precision/recall metrics
6. Track calibration data for model selection

Architecture:
- Reads search results JSON from stdin (output of run_search.py)
- For each conversation, launches TWO independent explorations
- Explorations only see issue summary, NOT our search results
- Uses Anthropic API for programmatic Claude Code invocations
- Outputs comprehensive evaluation results with per-conversation metrics
"""

import asyncio
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from anthropic import Anthropic


# Configuration
CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

REPOS_PATH = CONFIG["repos_path"]
APPROVED_REPOS = CONFIG["approved_repos"]
MODELS = CONFIG["models"]
CALIBRATION_ITERATIONS = CONFIG["calibration_iterations"]

# Anthropic client - require API key early to fail fast
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("Error: ANTHROPIC_API_KEY environment variable must be set", file=sys.stderr)
    sys.exit(1)
client = Anthropic(api_key=ANTHROPIC_API_KEY)


@dataclass
class FileReference:
    """A reference to a file in a specific repo."""

    repo: str
    path: str  # Relative path within repo

    def __str__(self) -> str:
        return f"{self.repo}/{self.path}"

    def __hash__(self) -> int:
        return hash((self.repo, self.path))

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, FileReference):
            return False
        return self.repo == other.repo and self.path == other.path


@dataclass
class ExplorationResult:
    """Results from a single exploration run."""

    model_used: str
    files_found: list[FileReference]
    exploration_log: str
    error: str | None = None


@dataclass
class JudgmentResult:
    """Judge's verdict on a file's relevance."""

    file_ref: FileReference
    relevant: bool
    actionable: str  # "yes", "no", "maybe"
    reasoning: str


@dataclass
class GroundTruthAnalysis:
    """Analysis of search results vs ground truth."""

    conversation_id: str
    issue_summary: str
    product_area: str

    # Ground truth construction
    run_a: ExplorationResult
    run_b: ExplorationResult
    ground_truth_files: list[FileReference]

    # Our search results
    our_files: list[FileReference]

    # Set comparisons
    intersection: list[FileReference]
    our_unique: list[FileReference]
    ground_truth_unique: list[FileReference]

    # Judgment of our unique files
    our_unique_judgments: list[JudgmentResult]

    # Metrics
    precision: float
    recall: float

    # Calibration data
    opus_only: list[FileReference]
    sonnet_only: list[FileReference]
    both_models: list[FileReference]


def parse_file_references(files_list: list[str]) -> list[FileReference]:
    """
    Parse file paths into FileReference objects.

    Expected format: "repo/path/to/file.ext"
    """
    refs = []
    for file_str in files_list:
        parts = file_str.split("/", 1)
        if len(parts) == 2:
            repo, path = parts
            if repo in APPROVED_REPOS:
                refs.append(FileReference(repo=repo, path=path))
    return refs


async def explore_codebase(
    conversation_id: str,
    issue_summary: str,
    model: str,
    run_label: str,
) -> ExplorationResult:
    """
    Launch an independent Claude Code exploration.

    The exploration prompt instructs Claude Code to:
    - Search the Tailwind codebases for ALL relevant code
    - Report file paths with repo prefix
    - NOT see our search results (independent ground truth)
    """
    exploration_prompt = f"""Given this customer issue from Intercom conversation {conversation_id}:

{issue_summary}

Your task: Explore the Tailwind codebases to find ALL code relevant to investigating or fixing this customer issue.

Available codebases (located at {REPOS_PATH}):
{', '.join(APPROVED_REPOS)}

Search strategy:
- Use Grep, Glob, and Read tools to explore code
- Look for feature implementations related to symptoms
- Find API handlers, services, data models
- Locate configuration, constants, and test files
- Consider multiple product areas if issue is ambiguous

Output format:
For each relevant file found, report the path with repo prefix:
Example: "aero/app/services/pins_service.rb"

Report ALL files you find as a JSON list at the end:
{{"files": ["repo/path/file1", "repo/path/file2", ...]}}

BEGIN EXPLORATION.
"""

    try:
        # Use Anthropic Messages API to simulate Claude Code exploration
        # In production, this would integrate with actual Claude Code runtime
        # For now, use the API with extended thinking for codebase reasoning
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            temperature=0.0,
            system=(
                "You are a software engineer analyzing a customer support issue. "
                "You have access to multiple codebases and need to find ALL relevant code files. "
                "Be thorough and systematic in your exploration."
            ),
            messages=[{"role": "user", "content": exploration_prompt}],
        )

        # Parse response for file references
        content = response.content[0].text if response.content else ""

        # Extract JSON file list from response
        files_found = []
        try:
            # Look for JSON block in response
            import re

            json_match = re.search(r'\{"files":\s*\[(.*?)\]\}', content, re.DOTALL)
            if json_match:
                files_json = json.loads(f'{{"files": [{json_match.group(1)}]}}')
                files_found = parse_file_references(files_json["files"])
        except (json.JSONDecodeError, KeyError) as e:
            print(
                f"Warning: Could not parse file list from {run_label}: {e}",
                file=sys.stderr,
            )

        return ExplorationResult(
            model_used=model,
            files_found=files_found,
            exploration_log=content,
            error=None,
        )

    except Exception as e:
        return ExplorationResult(
            model_used=model,
            files_found=[],
            exploration_log="",
            error=str(e),
        )


async def judge_our_unique_files(
    our_unique: list[FileReference],
    ground_truth: list[FileReference],
    issue_summary: str,
) -> list[JudgmentResult]:
    """
    Use judge model to determine relevance of files only we found.

    Judge sees:
    - Ground truth files (from dual exploration)
    - Our unique files
    - Original issue summary

    Judge determines:
    - Is each of our files relevant to the issue?
    - Is it actionable for fixing the bug?
    - Reasoning for verdict
    """
    if not our_unique:
        return []

    judge_prompt = f"""Issue Summary:
{issue_summary}

Ground Truth Files (found by independent exploration):
{chr(10).join(str(f) for f in ground_truth)}

Additional Files (found by our search logic):
{chr(10).join(str(f) for f in our_unique)}

Task: For each of our additional files, judge:
1. relevant: Is it relevant to the customer issue? (true/false)
2. actionable: Is it actionable for fixing the bug? ("yes"/"no"/"maybe")
3. reasoning: Brief explanation (1-2 sentences)

Output format:
{{
  "judgments": [
    {{"file": "repo/path", "relevant": true, "actionable": "yes", "reasoning": "..."}},
    ...
  ]
}}
"""

    try:
        response = client.messages.create(
            model=MODELS["judge"],
            max_tokens=2048,
            temperature=0.0,
            system=(
                "You are an experienced software engineer judging file relevance. "
                "Be strict: only mark files as relevant if they directly relate to the issue. "
                "Consider actionability: can an engineer use this file to fix the problem?"
            ),
            messages=[{"role": "user", "content": judge_prompt}],
        )

        content = response.content[0].text if response.content else ""

        # Parse JSON response
        import re

        json_match = re.search(r'\{.*"judgments".*\}', content, re.DOTALL)
        if json_match:
            judgments_data = json.loads(json_match.group(0))

            results = []
            for item in judgments_data.get("judgments", []):
                file_str = item["file"]
                parts = file_str.split("/", 1)
                if len(parts) == 2:
                    repo, path = parts
                    file_ref = FileReference(repo=repo, path=path)
                    results.append(
                        JudgmentResult(
                            file_ref=file_ref,
                            relevant=item.get("relevant", False),
                            actionable=item.get("actionable", "no"),
                            reasoning=item.get("reasoning", ""),
                        )
                    )
            return results

    except Exception as e:
        print(f"Warning: Judge failed: {e}", file=sys.stderr)

    # Fallback: mark all as not relevant if judge fails
    return [
        JudgmentResult(
            file_ref=f,
            relevant=False,
            actionable="no",
            reasoning="Judge failed to evaluate",
        )
        for f in our_unique
    ]


async def evaluate_conversation(
    conversation: dict[str, Any],
    iteration_number: int,
) -> GroundTruthAnalysis:
    """
    Evaluate a single conversation using dual exploration.

    Process:
    1. Launch Run A (Opus)
    2. Launch Run B (Sonnet during calibration, else Opus)
    3. Construct ground truth = union(run_a, run_b)
    4. Compare our search results vs ground truth
    5. Judge our unique files
    6. Calculate precision/recall
    """
    conversation_id = conversation["conversation_id"]
    issue_summary = conversation["issue_summary"]
    product_area = conversation.get("product_area", "unknown")

    # Handle both dict format (from run_search.py) and string format
    files_raw = conversation.get("search_results", {}).get("files_found", [])
    if files_raw and isinstance(files_raw[0], dict):
        # run_search.py outputs dicts with "path" key
        file_paths = [f["path"] for f in files_raw]
    else:
        file_paths = files_raw
    our_files = parse_file_references(file_paths)

    print(f"Evaluating conversation {conversation_id}...", file=sys.stderr)

    # Determine models for dual exploration
    model_a = MODELS["exploration_opus"]
    model_b = (
        MODELS["exploration_sonnet"]
        if iteration_number <= CALIBRATION_ITERATIONS
        else MODELS["exploration_opus"]
    )

    # Launch dual exploration in parallel
    run_a_task = explore_codebase(conversation_id, issue_summary, model_a, "Run A")
    run_b_task = explore_codebase(conversation_id, issue_summary, model_b, "Run B")

    run_a, run_b = await asyncio.gather(run_a_task, run_b_task)

    # Construct ground truth from union
    ground_truth_set = set(run_a.files_found) | set(run_b.files_found)
    ground_truth_files = sorted(ground_truth_set, key=str)

    # Set comparisons
    our_set = set(our_files)
    intersection = sorted(our_set & ground_truth_set, key=str)
    our_unique = sorted(our_set - ground_truth_set, key=str)
    ground_truth_unique = sorted(ground_truth_set - our_set, key=str)

    # Judge our unique files
    our_unique_judgments = await judge_our_unique_files(
        our_unique,
        ground_truth_files,
        issue_summary,
    )

    # Calculate metrics
    our_unique_relevant = sum(1 for j in our_unique_judgments if j.relevant)
    total_we_found = len(our_files)
    total_ground_truth = len(ground_truth_files)

    precision = (
        (len(intersection) + our_unique_relevant) / total_we_found
        if total_we_found > 0
        else 0.0
    )
    recall = (
        (len(intersection) + our_unique_relevant)
        / (len(intersection) + our_unique_relevant + len(ground_truth_unique))
        if (len(intersection) + our_unique_relevant + len(ground_truth_unique)) > 0
        else 0.0
    )

    # Calibration data (for model selection)
    opus_only = []
    sonnet_only = []
    both_models = []

    if iteration_number <= CALIBRATION_ITERATIONS and model_a != model_b:
        set_a = set(run_a.files_found)
        set_b = set(run_b.files_found)
        opus_only = sorted(set_a - set_b, key=str)
        sonnet_only = sorted(set_b - set_a, key=str)
        both_models = sorted(set_a & set_b, key=str)

    return GroundTruthAnalysis(
        conversation_id=conversation_id,
        issue_summary=issue_summary,
        product_area=product_area,
        run_a=run_a,
        run_b=run_b,
        ground_truth_files=ground_truth_files,
        our_files=our_files,
        intersection=intersection,
        our_unique=our_unique,
        ground_truth_unique=ground_truth_unique,
        our_unique_judgments=our_unique_judgments,
        precision=precision,
        recall=recall,
        opus_only=opus_only,
        sonnet_only=sonnet_only,
        both_models=both_models,
    )


def calculate_aggregate_metrics(
    analyses: list[GroundTruthAnalysis],
) -> dict[str, Any]:
    """
    Calculate aggregate metrics across all conversations.

    Includes:
    - Overall precision/recall
    - Per-product-area breakdown
    - Calibration data (model overlap rate)
    """
    if not analyses:
        return {}

    # Aggregate precision/recall
    total_precision = sum(a.precision for a in analyses)
    total_recall = sum(a.recall for a in analyses)
    avg_precision = total_precision / len(analyses)
    avg_recall = total_recall / len(analyses)

    # Per-product-area metrics
    by_area = defaultdict(list)
    for analysis in analyses:
        by_area[analysis.product_area].append(analysis)

    area_metrics = {}
    for area, area_analyses in by_area.items():
        area_precision = sum(a.precision for a in area_analyses) / len(area_analyses)
        area_recall = sum(a.recall for a in area_analyses) / len(area_analyses)
        area_metrics[area] = {
            "precision": round(area_precision, 3),
            "recall": round(area_recall, 3),
            "count": len(area_analyses),
        }

    # Calibration data
    calibration_data = None
    calibration_analyses = [
        a for a in analyses if a.opus_only or a.sonnet_only or a.both_models
    ]

    if calibration_analyses:
        total_opus_only = sum(len(a.opus_only) for a in calibration_analyses)
        total_sonnet_only = sum(len(a.sonnet_only) for a in calibration_analyses)
        total_both = sum(len(a.both_models) for a in calibration_analyses)
        total_opus = total_opus_only + total_both
        total_sonnet = total_sonnet_only + total_both

        overlap_rate = total_both / total_opus if total_opus > 0 else 0.0

        calibration_data = {
            "opus_only_files": total_opus_only,
            "sonnet_only_files": total_sonnet_only,
            "both_models_files": total_both,
            "overlap_rate": round(overlap_rate, 3),
            "recommendation": (
                "Use dual-Sonnet for iterations 3+"
                if overlap_rate >= CONFIG["calibration_overlap_threshold"]
                else "Keep Opus-Sonnet hybrid or Opus-only"
            ),
        }

    return {
        "aggregate": {
            "precision": round(avg_precision, 3),
            "recall": round(avg_recall, 3),
            "conversations_evaluated": len(analyses),
        },
        "by_product_area": area_metrics,
        "calibration": calibration_data,
    }


def serialize_analysis(analysis: GroundTruthAnalysis) -> dict[str, Any]:
    """Convert GroundTruthAnalysis to JSON-serializable dict."""
    return {
        "conversation_id": analysis.conversation_id,
        "issue_summary": analysis.issue_summary,
        "product_area": analysis.product_area,
        "run_a": {
            "model": analysis.run_a.model_used,
            "files_found": [str(f) for f in analysis.run_a.files_found],
            "error": analysis.run_a.error,
        },
        "run_b": {
            "model": analysis.run_b.model_used,
            "files_found": [str(f) for f in analysis.run_b.files_found],
            "error": analysis.run_b.error,
        },
        "ground_truth_files": [str(f) for f in analysis.ground_truth_files],
        "our_files": [str(f) for f in analysis.our_files],
        "intersection": [str(f) for f in analysis.intersection],
        "our_unique": [str(f) for f in analysis.our_unique],
        "ground_truth_unique": [str(f) for f in analysis.ground_truth_unique],
        "our_unique_judgments": [
            {
                "file": str(j.file_ref),
                "relevant": j.relevant,
                "actionable": j.actionable,
                "reasoning": j.reasoning,
            }
            for j in analysis.our_unique_judgments
        ],
        "precision": round(analysis.precision, 3),
        "recall": round(analysis.recall, 3),
        "calibration_data": {
            "opus_only": [str(f) for f in analysis.opus_only],
            "sonnet_only": [str(f) for f in analysis.sonnet_only],
            "both_models": [str(f) for f in analysis.both_models],
        }
        if analysis.opus_only or analysis.sonnet_only or analysis.both_models
        else None,
    }


async def main():
    """
    Main orchestrator.

    Reads search results from stdin, evaluates each conversation,
    outputs comprehensive evaluation results to stdout.
    """
    # Read search results from stdin
    try:
        search_results = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON from stdin: {e}", file=sys.stderr)
        sys.exit(1)

    conversations = search_results.get("conversations", [])
    iteration_number = search_results.get("iteration_number", 1)

    if not conversations:
        print("Error: No conversations to evaluate", file=sys.stderr)
        sys.exit(1)

    print(f"Evaluating {len(conversations)} conversations...", file=sys.stderr)

    # Evaluate all conversations
    analyses = []
    for conversation in conversations:
        try:
            analysis = await evaluate_conversation(conversation, iteration_number)
            analyses.append(analysis)
        except Exception as e:
            print(
                f"Error evaluating conversation {conversation.get('conversation_id')}: {e}",
                file=sys.stderr,
            )

    # Calculate aggregate metrics
    metrics = calculate_aggregate_metrics(analyses)

    # Output results
    output = {
        "iteration_number": iteration_number,
        "timestamp": search_results.get("timestamp"),
        "metrics": metrics,
        "conversations": [serialize_analysis(a) for a in analyses],
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
