# Security Audit: PR #99 - Milestone 6 Canonical Pipeline Consolidation

**Reviewer**: Sanjay (Security Auditor)
**Date**: 2026-01-21
**Round**: 1
**Verdict**: CONDITIONAL APPROVAL - 3 security concerns identified

---

## Executive Summary

PR #99 wires quality gates into `StoryCreationService`, retires `PipelineIntegrationService`, and aligns documentation with the canonical pipeline. The changes are primarily internal refactoring with minimal external attack surface expansion. However, I have identified **3 security concerns** that warrant attention, ranging from informational to medium severity.

---

## Files Reviewed

| File                                                    | Risk Profile | Notes                                 |
| ------------------------------------------------------- | ------------ | ------------------------------------- |
| `src/story_tracking/services/story_creation_service.py` | **Medium**   | Core logic, database writes, file I/O |
| `src/story_tracking/services/__init__.py`               | **Low**      | Export changes only                   |
| `tests/test_story_creation_service.py`                  | **Low**      | Test code, not production             |

---

## Security Findings

### S1: Exception Details Exposed in Error Messages [MEDIUM]

**Location**: `src/story_tracking/services/story_creation_service.py:1374-1394`

**Finding**: When classification-guided exploration fails, the exception details (including type and message) are captured and stored in the `code_context` dict, which may persist to the database:

```python
except Exception as e:
    import traceback
    error_details = f"{type(e).__name__}: {str(e)}"
    logger.warning(
        f"Classification-guided exploration failed: {error_details}",
        exc_info=True,
        ...
    )
    return {
        ...
        "success": False,
        "error": error_details,  # <-- Stored in DB
    }
```

**Risk**: Exception messages can leak internal implementation details, file paths, or configuration information. If the `code_context` is ever exposed through an API (e.g., story detail endpoint), this could provide attackers with reconnaissance information.

**Examples of potential leakage**:

- Database connection errors may reveal hostnames
- File not found errors reveal internal path structures
- Import errors reveal dependency versions

**Recommendation**:

1. Sanitize error messages before storage - use a generic "Exploration failed" message
2. Log full details for debugging but store sanitized version
3. Review API endpoints to ensure `code_context.error` is not exposed to unauthenticated users

---

### S2: Unbounded Input in JSON File Processing [LOW-MEDIUM]

**Location**: `src/story_tracking/services/story_creation_service.py:1039-1084`

**Finding**: The `_load_pm_results()` and `_load_extraction_data()` methods read JSON files without size validation:

```python
def _load_pm_results(self, path: Path) -> List[PMReviewResult]:
    with open(path) as f:
        data = json.load(f)  # No size limit

def _load_extraction_data(self, path: Path) -> Dict[str, List[ConversationData]]:
    with open(path) as f:
        for line in f:
            item = json.loads(line)  # No size limit per line
```

**Risk**: While these methods process files from the local filesystem (reducing direct attack surface), a compromised or malicious PM review file could:

1. Exhaust memory with extremely large JSON arrays
2. Create denial-of-service conditions
3. Potentially trigger JSON parsing vulnerabilities in edge cases

**Context**: These paths are used by the CLI/batch processing paths, not the UI API path. The primary `process_theme_groups()` method takes in-memory dicts and is not affected.

**Recommendation**:

1. Add file size validation before loading (e.g., reject files > 100MB)
2. Consider streaming JSON parsing for extraction JSONL files
3. Add a maximum item count limit when iterating

---

### S3: Logging of Potentially Sensitive Theme Data [LOW]

**Location**: Throughout `src/story_tracking/services/story_creation_service.py`

**Finding**: Multiple log statements include theme data, signatures, and failure reasons that may contain customer-originated content:

```python
# Line 452-455
logger.info(
    f"Quality gate FAIL (validation) for '{signature}': "
    f"{result.failure_reason}"
)

# Line 540-543
logger.info(
    f"Routing '{signature}' to orphan integration: {failure_reason} "
    f"({len(conversations)} conversations)"
)
```

**Risk**: If signatures or failure reasons contain customer PII or sensitive business data (e.g., "billing_customer_xyz_payment_failure"), this could be logged to systems with different retention/access policies than the database.

**Mitigating Factor**: Signatures are typically derived from issue categories (e.g., "billing_invoice_download_error") rather than customer data, so this is **low severity** in practice.

**Recommendation**:

1. Review signature generation to ensure no PII leakage
2. Consider truncating signatures in logs (e.g., first 50 chars + "...")
3. Document log data classification for compliance

---

## Security Positives

### Existing Security Controls

1. **Codebase Security Module**: The project has `codebase_security.py` with:
   - Path traversal protection (`validate_path()`)
   - Repository allowlist (`validate_repo_name()`)
   - Sensitive file filtering (`is_sensitive_file()`)
   - Secret redaction (`redact_secrets()`)
   - Command injection prevention (`validate_git_command_args()`)

2. **Input Validation for Conversation IDs**: Good defensive check added:

   ```python
   # Line 591-594
   conv_id = str(conv_dict.get("id", "")).strip()
   if not conv_id:
       raise ValueError(f"Empty conversation ID in theme group '{signature}'")
   ```

3. **Exception Handling for Interrupts**: Proper handling prevents swallowing system signals:

   ```python
   # Line 389-390
   except (KeyboardInterrupt, SystemExit):
       raise  # Never swallow these
   ```

4. **Parameterized SQL Queries**: Database interaction uses parameterized queries:

   ```python
   # Line 780-783
   cur.execute("""
       UPDATE stories SET pipeline_run_id = %s WHERE id = %s
   """, (pipeline_run_id, str(story_id)))
   ```

5. **Code Snippet Size Limits**: Prevents storage bloat from oversized content:
   ```python
   MAX_CODE_SNIPPET_LENGTH = 5000  # 5KB per snippet
   MAX_CODE_CONTEXT_SIZE = 1_000_000  # 1MB total
   ```

---

## OWASP Top 10 Assessment

| Category                       | Risk    | Notes                                 |
| ------------------------------ | ------- | ------------------------------------- |
| A01: Broken Access Control     | **N/A** | No auth changes in this PR            |
| A02: Cryptographic Failures    | **N/A** | No crypto in this code                |
| A03: Injection                 | **Low** | SQL uses parameterized queries        |
| A04: Insecure Design           | **Low** | Quality gates add defensive layers    |
| A05: Security Misconfiguration | **Low** | Error messages could leak info (S1)   |
| A06: Vulnerable Components     | **N/A** | No new dependencies                   |
| A07: Authentication Failures   | **N/A** | No auth in this code path             |
| A08: Data Integrity Failures   | **Low** | JSON loading without size limits (S2) |
| A09: Security Logging Failures | **Low** | Potential PII in logs (S3)            |
| A10: SSRF                      | **N/A** | No outbound requests from this code   |

---

## Test Coverage Assessment

The test file (`tests/test_story_creation_service.py`) has **786 new lines** with comprehensive coverage including:

- Quality gate pass/fail scenarios
- Boundary testing for confidence thresholds (49.9, 50.0, 50.1)
- Orphan routing fallback behavior
- Empty/missing field handling
- Error decision handling

**Positive**: Test for empty conversation ID validation exists (`test_rejects_empty_conversation_id`).

**Gap**: No explicit tests for:

- Malformed JSON input handling
- Oversized input rejection
- Exception message sanitization

---

## Recommendations Summary

| ID  | Severity | Recommendation                               | Effort |
| --- | -------- | -------------------------------------------- | ------ |
| S1  | Medium   | Sanitize exception details before DB storage | Small  |
| S2  | Low      | Add file size validation for JSON loading    | Small  |
| S3  | Low      | Review signature content for PII compliance  | Small  |

---

## Verdict

**CONDITIONAL APPROVAL**: The code demonstrates good security practices overall (parameterized queries, path validation, input validation). The identified issues are not blocking for merge but should be addressed in follow-up work.

**Required before merge**: None (issues are low-medium severity enhancements)

**Recommended follow-up**:

1. File GitHub issue for S1 (error message sanitization)
2. Consider S2/S3 in next security hardening pass

---

_Reviewed by Sanjay, Security Auditor_
_"Assume all input is malicious"_
