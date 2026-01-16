#!/usr/bin/env python3
"""
Codebase Search VDD - Dual Exploration Evaluator v2 (CLI-based)

Uses Claude CLI (via subprocess) for codebase exploration instead of SDK tool-use.
This is significantly faster because Claude CLI handles filesystem operations
internally without API round-trips for each tool call.

Architecture:
- Reads search results JSON from stdin (output of run_search.py)
- For each conversation, spawns TWO Claude CLI processes for exploration
- Explorations only see issue summary, NOT our search results
- Outputs comprehensive evaluation results with per-conversation metrics
"""

import asyncio
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# No longer using anthropic SDK - all calls go through Claude CLI


# Configuration
CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

REPOS_PATH = Path(CONFIG["repos_path"])
APPROVED_REPOS = CONFIG["approved_repos"]
MODELS = CONFIG["models"]
CALIBRATION_ITERATIONS = CONFIG["calibration_iterations"]
OUTPUT_DIR = Path(__file__).parent / "outputs"

# Valid model names (for command injection prevention)
VALID_MODELS = frozenset(MODELS.values())


def validate_model(model: str) -> str:
    """Validate model string against known safe values to prevent command injection."""
    if model not in VALID_MODELS:
        raise ValueError(f"Invalid model: {model}. Must be one of {VALID_MODELS}")
    return model


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
    duration_seconds: float
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


def extract_files_from_output_with_diagnostics(output: str) -> tuple[list[str], dict[str, list[str]]]:
    """
    Extract file paths from Claude CLI output WITH diagnostic info.

    Prioritizes JSON extraction (more reliable), falls back to regex patterns.

    Returns:
        tuple: (list of files, dict of pattern_name -> matches for debugging)
    """
    files = set()
    diagnostics = {
        "json_structured": [],
        "pattern1_relative": [],
        "pattern2_absolute": [],
        "pattern3_json_array": [],
        "pattern4_bullets": [],
        "pattern5_backticks": [],
    }

    # Priority 1: Try to extract structured JSON with "relevant_files" key
    # Use a more targeted approach to avoid regex backtracking issues:
    # First check if the key exists, then extract a bounded substring
    if '"relevant_files"' in output:
        # Find the start of the JSON object containing relevant_files
        key_idx = output.find('"relevant_files"')
        # Look for opening brace before the key (bounded search)
        start_idx = output.rfind('{', max(0, key_idx - 100), key_idx)
        if start_idx != -1:
            # Extract a reasonable chunk and try to parse
            # Limit to 50KB to prevent DoS on huge outputs
            chunk = output[start_idx:start_idx + 50000]
            # Find matching closing brace (simple counter approach)
            brace_count = 0
            end_idx = 0
            for i, c in enumerate(chunk):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            if end_idx > 0:
                json_str = chunk[:end_idx]
                try:
                    data = json.loads(json_str)
                    json_files = data.get("relevant_files", [])
                    if json_files:
                        for f in json_files:
                            if isinstance(f, str) and '/' in f:
                                # Validate it starts with approved repo
                                if any(f.startswith(r + '/') for r in APPROVED_REPOS):
                                    diagnostics["json_structured"].append(f)
                                    files.add(f)
                        # If we got JSON files, return early - no need for regex fallback
                        if files:
                            return list(files), diagnostics
                except json.JSONDecodeError:
                    pass  # Fall through to regex patterns

    # Fallback: Regex patterns for backward compatibility and edge cases

    # Pattern 1: Look for file paths with known repo prefixes (relative paths)
    for repo in APPROVED_REPOS:
        pattern = rf'\b{repo}/[\w\-./]+\.\w+'
        matches = re.findall(pattern, output)
        diagnostics["pattern1_relative"].extend(matches)
        files.update(matches)

    # Pattern 2: Look for ABSOLUTE paths and extract repo-relative portion
    for repo in APPROVED_REPOS:
        pattern = rf'[`\s](/[^\s`]*/{repo}/[\w\-./]+\.\w+)'
        matches = re.findall(pattern, output)
        for match in matches:
            idx = match.find(f'/{repo}/')
            if idx != -1:
                relative_path = match[idx + 1:]
                diagnostics["pattern2_absolute"].append(f"{match} -> {relative_path}")
                files.add(relative_path)

    # Pattern 3: Look for JSON-like arrays of files (legacy format)
    json_pattern = r'\[([^\]]+)\]'
    for match in re.findall(json_pattern, output):
        items = re.findall(r'"([^"]+)"', match)
        for item in items:
            if '/' in item and any(item.startswith(r + '/') for r in APPROVED_REPOS):
                diagnostics["pattern3_json_array"].append(item)
                files.add(item)

    # Pattern 4: Markdown bullet points with file paths
    bullet_pattern = r'[-*•]\s+`?([a-z]+/[\w\-./]+\.\w+)`?'
    for match in re.findall(bullet_pattern, output, re.IGNORECASE):
        if any(match.startswith(r + '/') for r in APPROVED_REPOS):
            diagnostics["pattern4_bullets"].append(match)
            files.add(match)

    # Pattern 5: Backtick-wrapped paths (for edge cases)
    backtick_pattern = r'`([a-z]+/[\w\-./]+\.\w+)`'
    for match in re.findall(backtick_pattern, output, re.IGNORECASE):
        if any(match.startswith(r + '/') for r in APPROVED_REPOS):
            diagnostics["pattern5_backticks"].append(match)
            files.add(match)

    return list(files), diagnostics


def extract_files_from_output(output: str) -> list[str]:
    """
    Extract file paths from Claude CLI output.

    Looks for patterns like:
    - repo/path/to/file.ext (relative)
    - /full/path/to/repo/path/to/file.ext (absolute)
    - Bullet points with file paths
    - JSON arrays of files
    - Backtick-wrapped paths
    """
    files, _ = extract_files_from_output_with_diagnostics(output)
    return files


async def explore_codebase_cli(
    conversation_id: str,
    issue_summary: str,
    model: str,
    run_label: str,
) -> ExplorationResult:
    """
    Launch a Claude CLI process for codebase exploration.

    Uses `claude` command in interactive mode (via stdin) to explore the
    Tailwind codebases. This uses the subscription, not API credits.
    """
    # Validate model to prevent command injection
    model = validate_model(model)

    exploration_prompt = f"""Given this customer issue from Intercom conversation {conversation_id}:

{issue_summary}

Your task: Explore the Tailwind codebases to find ALL code relevant to investigating or fixing this customer issue.

Available codebases at {REPOS_PATH}: {', '.join(APPROVED_REPOS)}

Search strategy:
1. Use Grep to find keywords related to the issue symptoms
2. Use Glob to find files in relevant directories
3. Read key files to verify relevance
4. Focus on feature implementations, API handlers, services, data models

Be thorough but efficient. Include:
- Feature implementations related to symptoms
- API handlers, services, data models
- Configuration and constants
- Test files that show expected behavior

BEGIN EXPLORATION.

═══════════════════════════════════════════════════════════════
CRITICAL OUTPUT REQUIREMENT (DO NOT SKIP)
═══════════════════════════════════════════════════════════════

Your FINAL message MUST end with a JSON object containing the files you found.
Use repo-relative paths (NOT absolute paths like /Users/...).

Output format - a JSON object with "relevant_files" array:
{{"relevant_files": ["repo/path/to/file.ext", "repo/path/to/other.ext"]}}

Example:
{{"relevant_files": ["aero/packages/tailwindapp/client/components/example.tsx", "tack/service/lib/handlers/api/example-handler.ts"]}}

DO NOT output a summary statement instead of JSON.
DO NOT wrap JSON in markdown code blocks.
If valid JSON is not present, your exploration will be DISCARDED.
"""

    start_time = datetime.now()

    # Build claude command
    # Using interactive mode via stdin (no --print) to use subscription, not API credits
    # --model still works to select the model
    cmd = [
        "claude",
        "--model", model,
        "--dangerously-skip-permissions",
    ]

    try:
        # Run claude CLI with timeout, passing prompt via stdin
        # This runs an interactive session that uses the subscription
        result = subprocess.run(
            cmd,
            input=exploration_prompt,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for interactive exploration
            cwd=str(REPOS_PATH),  # Run from repos directory
        )

        duration = (datetime.now() - start_time).total_seconds()
        output = result.stdout + result.stderr

        # IMMEDIATE LOG: Write raw output to file for debugging (even if process is killed later)
        log_dir = OUTPUT_DIR / f"iteration_{CONFIG.get('current_iteration', 0)}" / "exploration_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"{conversation_id}_{run_label}_{model.replace('/', '_')}.txt"
        with open(log_file, 'w') as f:
            f.write(f"=== Exploration Log ===\n")
            f.write(f"Conversation: {conversation_id}\n")
            f.write(f"Model: {model}\n")
            f.write(f"Duration: {duration:.1f}s\n")
            f.write(f"Exit code: {result.returncode}\n")
            f.write(f"\n=== Raw Output ({len(output)} chars) ===\n")
            f.write(output)
            f.write(f"\n\n=== Extraction Diagnostics ===\n")

        # Extract files from output with diagnostics
        files_list, extraction_diagnostics = extract_files_from_output_with_diagnostics(output)
        files_found = parse_file_references(files_list)

        # Append diagnostics to log
        with open(log_file, 'a') as f:
            f.write(f"Files extracted: {len(files_list)}\n")
            for pattern_name, matches in extraction_diagnostics.items():
                f.write(f"  {pattern_name}: {len(matches)} matches\n")
                for m in matches[:5]:  # Show first 5
                    f.write(f"    - {m}\n")
            if not files_list:
                f.write("\n=== NO FILES EXTRACTED - Showing output sample ===\n")
                f.write(output[:3000])

        # WARN if 0 files extracted - check for format compliance issue
        if not files_list:
            has_json_format = '"relevant_files"' in output.lower()
            has_legacy_format = bool(re.search(r'relevant\s*files\s*:?', output, re.IGNORECASE))
            if not has_json_format and not has_legacy_format and duration > 60:
                # Model explored but didn't output in required format
                print(f"    ⚠️  FORMAT ERROR: Model did not output required JSON format!", file=sys.stderr)
                print(f"    Output was {len(output)} chars after {duration:.0f}s exploration.", file=sys.stderr)
                print(f"    Expected: {{\"relevant_files\": [...]}}", file=sys.stderr)
                print(f"    Check log: {log_file}", file=sys.stderr)
                # Mark as format error in log
                with open(log_file, 'a') as f:
                    f.write("\n=== FORMAT ERROR ===\n")
                    f.write("Model did not output required JSON format.\n")
                    f.write("Expected: {\"relevant_files\": [...]}\n")
                    f.write("This run will be marked as FORMAT_ERROR.\n")
            elif len(output) > 100:
                # Has some output but still no files - could be parsing issue
                print(f"    WARNING: 0 files extracted from {len(output)} chars of output!", file=sys.stderr)
                print(f"    Check log: {log_file}", file=sys.stderr)
                # Look for common file path patterns that we might be missing
                potential_paths = re.findall(r'[\w\-./]+\.\w{2,4}', output)
                path_sample = [p for p in potential_paths if '/' in p][:10]
                if path_sample:
                    print(f"    Potential paths found but not matched: {path_sample}", file=sys.stderr)

        # Log error output if command failed
        if result.returncode != 0:
            print(f"    ERROR in {run_label}: Exit code {result.returncode}", file=sys.stderr)
            print(f"    stdout: {result.stdout[:500] if result.stdout else 'empty'}", file=sys.stderr)
            print(f"    stderr: {result.stderr[:500] if result.stderr else 'empty'}", file=sys.stderr)

        return ExplorationResult(
            model_used=model,
            files_found=files_found,
            exploration_log=output[:5000],  # Truncate log
            duration_seconds=duration,
            error=None if result.returncode == 0 else f"Exit code {result.returncode}",
        )

    except subprocess.TimeoutExpired:
        duration = (datetime.now() - start_time).total_seconds()
        return ExplorationResult(
            model_used=model,
            files_found=[],
            exploration_log="Exploration timed out after 5 minutes",
            duration_seconds=duration,
            error="Timeout",
        )
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        return ExplorationResult(
            model_used=model,
            files_found=[],
            exploration_log=str(e),
            duration_seconds=duration,
            error=str(e),
        )


async def judge_our_unique_files(
    our_unique: list[FileReference],
    ground_truth: list[FileReference],
    issue_summary: str,
) -> list[JudgmentResult]:
    """
    Use Claude CLI to determine relevance of files only we found.
    """
    if not our_unique:
        return []

    judge_prompt = f"""You are an experienced software engineer judging file relevance.
Be strict: only mark files as relevant if they directly relate to the issue.
Consider actionability: can an engineer use this file to fix the problem?

Issue Summary:
{issue_summary}

Ground Truth Files (found by independent exploration):
{chr(10).join(str(f) for f in ground_truth) if ground_truth else "(none found)"}

Additional Files (found by our search logic):
{chr(10).join(str(f) for f in our_unique)}

Task: For each of our additional files, judge:
1. relevant: Is it relevant to the customer issue? (true/false)
2. actionable: Is it actionable for fixing the bug? ("yes"/"no"/"maybe")
3. reasoning: Brief explanation (1-2 sentences)

Output ONLY valid JSON in this exact format (no other text):
{{
  "judgments": [
    {{"file": "repo/path", "relevant": true, "actionable": "yes", "reasoning": "..."}},
    ...
  ]
}}
"""

    try:
        # Validate model to prevent command injection
        judge_model = validate_model(MODELS["judge"])

        # Use Claude CLI for judging
        cmd = [
            "claude",
            "--print",
            "--model", judge_model,
            "--dangerously-skip-permissions",
            "-p", judge_prompt,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout for judge (needs time for 100+ files)
        )

        content = result.stdout

        # Parse JSON response
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

    except subprocess.TimeoutExpired:
        print("Warning: Judge timed out", file=sys.stderr)
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
    Evaluate a single conversation using dual CLI exploration.
    """
    conversation_id = conversation["conversation_id"]
    issue_summary = conversation["issue_summary"]
    product_area = conversation.get("product_area", "unknown")

    # Handle both dict format (from run_search.py) and string format
    files_raw = conversation.get("search_results", {}).get("files_found", [])
    if files_raw and isinstance(files_raw[0], dict):
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

    # Launch dual CLI exploration sequentially (parallel was causing issues)
    # TODO: Investigate if parallel execution can be restored
    run_a = await explore_codebase_cli(conversation_id, issue_summary, model_a, "Run A")
    run_b = await explore_codebase_cli(conversation_id, issue_summary, model_b, "Run B")

    print(f"  Run A ({model_a}): {len(run_a.files_found)} files in {run_a.duration_seconds:.1f}s", file=sys.stderr)
    print(f"  Run B ({model_b}): {len(run_b.files_found)} files in {run_b.duration_seconds:.1f}s", file=sys.stderr)

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

    # Calibration data
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
    """Calculate aggregate metrics across all conversations."""
    if not analyses:
        return {}

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

    # Total duration
    total_duration = sum(a.run_a.duration_seconds + a.run_b.duration_seconds for a in analyses)

    return {
        "aggregate": {
            "precision": round(avg_precision, 3),
            "recall": round(avg_recall, 3),
            "conversations_evaluated": len(analyses),
            "total_exploration_seconds": round(total_duration, 1),
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
            "duration_seconds": analysis.run_a.duration_seconds,
            "error": analysis.run_a.error,
            "exploration_log": analysis.run_a.exploration_log[:2000] if analysis.run_a.exploration_log else None,
        },
        "run_b": {
            "model": analysis.run_b.model_used,
            "files_found": [str(f) for f in analysis.run_b.files_found],
            "duration_seconds": analysis.run_b.duration_seconds,
            "error": analysis.run_b.error,
            "exploration_log": analysis.run_b.exploration_log[:2000] if analysis.run_b.exploration_log else None,
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

    print(f"Evaluating {len(conversations)} conversations with CLI exploration (v2)...", file=sys.stderr)

    # Evaluate all conversations
    analyses = []
    for conversation in conversations:
        try:
            analysis = await evaluate_conversation(conversation, iteration_number)
            analyses.append(analysis)
            print(f"  -> Precision: {analysis.precision:.2f}, Recall: {analysis.recall:.2f}", file=sys.stderr)
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
        "timestamp": datetime.utcnow().isoformat(),
        "evaluator_version": "v2-cli",
        "metrics": metrics,
        "conversations": [serialize_analysis(a) for a in analyses],
    }

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
