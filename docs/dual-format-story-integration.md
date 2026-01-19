# Dual-Format Story Integration

Integration of DualStoryFormatter with StoryCreationService for Phase 3.3 of the dual-format story architecture.

## Overview

The `StoryCreationService` now supports generating dual-format stories (v2) with optional codebase context, while maintaining backward compatibility with the simple format (v1).

## Usage

### Basic Usage (v1 - Simple Format)

Default behavior - generates simple story descriptions without codebase context:

```python
from story_tracking.services import StoryCreationService, StoryService, OrphanService

# Initialize with default settings
service = StoryCreationService(
    story_service=story_service,
    orphan_service=orphan_service,
    # dual_format_enabled defaults to False
)

# Process PM review results - generates v1 format stories
result = service.process_pm_review_results(
    results_path=Path("pm_results.json"),
    extraction_path=Path("extraction.jsonl"),
)
```

### Dual-Format Stories (v2)

Enable dual-format with codebase context:

```python
from story_tracking.services import StoryCreationService

# Initialize with dual format enabled
service = StoryCreationService(
    story_service=story_service,
    orphan_service=orphan_service,
    dual_format_enabled=True,
    target_repo="aero",  # Repository name for codebase exploration
)

# Process PM review results - generates v2 format stories with:
# - Section 1: Human-facing engineering story
# - Section 2: AI agent task specification
# - Codebase context from exploration (if available)
result = service.process_pm_review_results(
    results_path=Path("pm_results.json"),
    extraction_path=Path("extraction.jsonl"),
)
```

## Features

### Graceful Degradation

The integration handles missing dependencies gracefully:

1. **Dependencies unavailable**: Falls back to simple format (v1) with warning log
2. **Exploration fails**: Continues with dual format but without codebase context
3. **No target_repo provided**: Uses dual format without exploration

### Format Detection

Stories include metadata indicating the format version:

- **v1**: Simple format (single section, no codebase context)
- **v2**: Dual format (human + AI sections, optional codebase context)

### Logging

The integration provides detailed logging:

```python
logger.info(f"Dual format enabled with target repo: {target_repo}")
logger.debug(f"Exploring codebase for {signature}")
logger.info(f"Codebase exploration complete: {files} files, {snippets} snippets")
logger.warning(f"Codebase exploration failed: {error}")
logger.info(f"Generated dual-format story (format_version: v2)")
```

## Architecture

### Components

1. **StoryCreationService**: Main service with dual-format support
2. **DualStoryFormatter**: Formats stories with human/AI sections
3. **CodebaseContextProvider**: Explores codebase for relevant context

### Data Flow

```
PM Review Results
  ↓
StoryCreationService._generate_description()
  ↓
[if dual_format_enabled]
  ↓
CodebaseContextProvider.explore_for_theme() → ExplorationResult
  ↓
_build_formatter_theme_data() → Formatter-compatible data
  ↓
DualStoryFormatter.format_story() → DualFormatOutput
  ↓
Story with dual-format description
```

## Testing

Comprehensive test coverage in `tests/test_story_creation_service.py`:

- ✅ Default backward compatibility (dual format disabled)
- ✅ Graceful degradation when dependencies unavailable
- ✅ Initialization with dual format enabled
- ✅ Description generation with exploration
- ✅ Exploration failure handling
- ✅ Simple format still works
- ✅ Theme data transformation
- ✅ End-to-end dual-format story creation

Run tests:

```bash
pytest tests/test_story_creation_service.py::TestDualFormatIntegration -v
```

## Configuration

### Environment Variables

```bash
# Optional: Override repository base path for codebase exploration
export REPO_BASE_PATH="/path/to/repos"
```

### Initialization Parameters

| Parameter             | Type          | Default  | Description                              |
| --------------------- | ------------- | -------- | ---------------------------------------- |
| `story_service`       | StoryService  | Required | Service for story CRUD operations        |
| `orphan_service`      | OrphanService | Required | Service for orphan CRUD operations       |
| `dual_format_enabled` | bool          | False    | Enable dual-format stories (v2)          |
| `target_repo`         | str \| None   | None     | Repository name for codebase exploration |

## Migration Guide

### Existing Code

If you're using StoryCreationService with the default settings, no changes required:

```python
# Existing code - still works exactly the same
service = StoryCreationService(story_service, orphan_service)
result = service.process_pm_review_results(pm_path)
```

### Enabling Dual Format

To enable dual format for new stories:

```python
# New code - opt-in to dual format
service = StoryCreationService(
    story_service,
    orphan_service,
    dual_format_enabled=True,
    target_repo="aero",  # or your target repository
)
result = service.process_pm_review_results(pm_path)
```

## Example Output

### v1 Format (Simple)

```markdown
**User Intent**: Cancel subscription

**Symptoms**: wants to cancel, billing issue

**Product Area**: billing

**Component**: subscription

**PM Review Reasoning**: All conversations about billing cancellation

_Signature_: `billing_cancellation_request`
```

### v2 Format (Dual)

```markdown
## SECTION 1: Human-Facing Story

# Story: Cancel Subscription

## User Story

As a **Tailwind user**
I want **to cancel my subscription**
So that **I stop being charged**

## Context

- **Product Area**: billing
- **Component**: subscription
- **Related Conversations**: 5 customer reports

## Acceptance Criteria

- [ ] User can successfully cancel subscription
- [ ] Billing stops immediately
- [ ] Confirmation email sent

---

## SECTION 2: AI Agent Task Specification

# Agent Task: Cancel Subscription

## Role & Context

This card is for a **senior backend engineer** working in the Tailwind codebase.

## Goal

Implement subscription cancellation flow

## Context & Architecture

### Relevant Files:

- `backend/billing/subscription.py` (lines 45-120) - Subscription management
- `backend/api/billing.py` (line 89) - Cancellation endpoint

### Code Snippets:

[Relevant code snippets with context]

## Instructions

1. **Analyze** the subscription code
2. **Implement** the cancellation flow
3. **Test** with sample data
   ...

---

_Generated by FeedForward Pipeline v2.0_
```

## References

- [Dual-Format Story Architecture](./architecture/dual-format-story-architecture.md) - Overall architecture
- [Story Formatter](../src/story_formatter.py) - DualStoryFormatter implementation
- [Codebase Context Provider](../src/story_tracking/services/codebase_context_provider.py) - Exploration logic
- [GitHub Issue #37](https://github.com/paulyokota/FeedForward/issues/37) - Original specification
