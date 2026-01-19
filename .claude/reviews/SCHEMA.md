# Review Output Schema

This document defines the structured output format for 5-personality code reviews.

## Directory Structure

```
.claude/reviews/
├── SCHEMA.md          # This file
└── PR-{number}/       # Created per PR
    ├── sanjay.json    # Compact findings
    ├── sanjay.md      # Verbose reasoning
    ├── reginald.json
    ├── reginald.md
    └── ...
```

## JSON Format (Compact Findings)

Each reviewer writes a `.json` file with this structure:

```json
{
  "reviewer": "sanjay",
  "pr_number": 38,
  "review_round": 1,
  "timestamp": "2026-01-19T20:45:00Z",
  "verdict": "BLOCK",
  "summary": "2 CRITICAL, 2 HIGH security issues found",
  "issues": [
    {
      "id": "S1",
      "severity": "CRITICAL",
      "confidence": "high",
      "category": "injection",
      "file": "scripts/apply_learnings.py",
      "lines": [262, 266],
      "title": "Command injection via model name parameter",
      "why": "Model name loaded from user-editable config.json is passed to subprocess without validation. Attacker controlling config can execute arbitrary commands.",
      "fix": "Hardcode VALID_MODELS allowlist in code, not config. Validate with regex: ^[a-zA-Z0-9.-]+$",
      "verify": "Check if config.json is user-editable in deployment",
      "scope": "isolated",
      "see_verbose": true
    }
  ]
}
```

### Field Definitions

| Field          | Type   | Required | Description                                           |
| -------------- | ------ | -------- | ----------------------------------------------------- |
| `reviewer`     | string | yes      | Reviewer name (sanjay, reginald, quinn, dmitri, maya) |
| `pr_number`    | number | yes      | PR number being reviewed                              |
| `review_round` | number | yes      | Which round of review (1, 2, 3...)                    |
| `timestamp`    | string | yes      | ISO 8601 timestamp                                    |
| `verdict`      | string | yes      | APPROVE, BLOCK, or COMMENT                            |
| `summary`      | string | yes      | One-line summary of findings                          |
| `issues`       | array  | yes      | List of issues found (can be empty)                   |

### Issue Fields

| Field         | Type    | Required | Description                                                           |
| ------------- | ------- | -------- | --------------------------------------------------------------------- |
| `id`          | string  | yes      | Short ID for reference (S1, S2 for Sanjay, R1, R2 for Reginald, etc.) |
| `severity`    | string  | yes      | CRITICAL, HIGH, MEDIUM, LOW                                           |
| `confidence`  | string  | yes      | high, medium, low - how sure is the reviewer                          |
| `category`    | string  | yes      | Issue category (injection, auth, performance, yagni, clarity, etc.)   |
| `file`        | string  | yes      | File path relative to repo root                                       |
| `lines`       | array   | yes      | [start_line, end_line] or [single_line]                               |
| `title`       | string  | yes      | Short description (~10 words)                                         |
| `why`         | string  | yes      | Attack vector / impact / reasoning (1-2 sentences)                    |
| `fix`         | string  | yes      | Concrete action to take (1-2 sentences)                               |
| `verify`      | string  | no       | Assumption to check before fixing                                     |
| `scope`       | string  | yes      | "isolated" or "systemic"                                              |
| `see_verbose` | boolean | yes      | Whether verbose MD has important additional detail                    |

### Severity Guidelines

- **CRITICAL**: Immediate security risk, data loss, or complete feature breakage
- **HIGH**: Significant bug, security concern, or major quality issue
- **MEDIUM**: Should fix but not blocking
- **LOW**: Nice to have, style issues, minor improvements

### Confidence Guidelines

- **high**: Verified the issue, clear evidence
- **medium**: Likely an issue but couldn't fully verify (flag in `verify`)
- **low**: Possible concern, reviewer may be missing context

## Markdown Format (Verbose Reasoning)

Each reviewer also writes a `.md` file with full context:

````markdown
# {Reviewer} Code Review - PR #{number} Round {n}

**Verdict**: BLOCK
**Date**: 2026-01-19

## Summary

{One paragraph overview}

---

## S1: Command injection via model name parameter

**Severity**: CRITICAL | **Confidence**: High | **Scope**: Isolated

**File**: `scripts/apply_learnings.py:262-266`

### The Problem

{Full explanation with data flow analysis}

### Attack Scenario

{Step by step exploitation}

### Current Code

```python
# Vulnerable code
model = CONFIG["models"]["judge"]
cmd = ["claude", "--model", model, ...]
```
````

### Suggested Fix

```python
# Fixed code
VALID_MODELS = frozenset(["claude-opus-4", "claude-sonnet-4"])
model = CONFIG["models"]["judge"]
if model not in VALID_MODELS:
    raise ValueError(f"Invalid model: {model}")
```

### Related Concerns

{Other files or patterns to check}

### References

{OWASP links, CVEs, documentation}

---

## S2: ...

{Next issue}

```

## Usage by Tech Lead

1. **Quick triage**: Read `*.json` files (~2-5KB each)
2. **Understand issue**: `why` field explains the reasoning
3. **Need more context**: Read corresponding `.md` file
4. **Track fixes**: Update issue status in subsequent rounds
```
