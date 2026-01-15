# AI Section Template

**Version**: 1.0
**Purpose**: Guide generation of AI-facing task specifications for dual-format story output
**Related**: GitHub Issue #37, Phase 3.2

---

## Base Template

```markdown
## SECTION 2: AI Agent Task Specification

# Agent Task: {{task_title}}

## Role & Context

You are a **{{role}}** working in the {{repository}} codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: {{repository}}
**Task Type**: {{task_type}}
**Related Story**: See Human-Facing Section above
**Priority**: {{priority}} ({{priority_reason}})

## Goal (Single Responsibility)

{{goal_description}}

## Context & Architecture

### Relevant Files:

{{#relevant_files}}

- `{{path}}`{{#line_range}} (lines {{line_start}}-{{line_end}}){{/line_range}} - {{relevance}}
  {{/relevant_files}}

{{#code_snippets}}

### Code Snippet: {{context}}

\`\`\`{{language}}
{{content}}
\`\`\`

_Source: `{{file_path}}:{{line_start}}-{{line_end}}`_

{{/code_snippets}}

### Architecture Notes:

{{architecture_notes}}

### Business Rules:

{{#business_rules}}

- {{.}}
  {{/business_rules}}

### Related Systems:

{{#related_systems}}

- {{.}}
  {{/related_systems}}

## Instructions (Step-by-Step)

{{#instructions}}
{{index}}. **{{title}}**
{{description}}
{{/instructions}}

## Success Criteria (Explicit & Observable)

{{#success_criteria}}

- [ ] {{.}}
      {{/success_criteria}}

## Guardrails & Constraints

### DO NOT:

{{#do_not}}

- {{.}}
  {{/do_not}}

### ALWAYS:

{{#always}}

- {{.}}
  {{/always}}

{{#extended_thinking}}

## Extended Thinking Guidance

{{extended_thinking}}
{{/extended_thinking}}

{{#investigation_queries}}

## Investigation Queries

{{#queries}}
\`\`\`sql
{{.}}
\`\`\`
{{/queries}}
{{/investigation_queries}}
```

---

## Default Values

### Role Defaults

```yaml
default_role: "senior backend engineer"
role_mapping:
  backend: "senior backend engineer"
  frontend: "senior frontend engineer"
  fullstack: "senior fullstack engineer"
  devops: "senior DevOps engineer"
  data: "senior data engineer"
```

### Task Type Defaults

```yaml
task_type_mapping:
  product_issue: "bug-fix"
  feature_request: "feature"
  usability_issue: "feature"
  performance_issue: "performance"
  security_issue: "security"
```

### Priority Defaults

```yaml
priority_levels:
  high: "3+ customer reports OR revenue-blocking"
  medium: "1-2 customer reports OR workflow friction"
  low: "Nice-to-have OR edge case"
```

### Standard Guardrails

```yaml
# DO NOT (common across all types)
do_not_defaults:
  - "Modify unrelated code outside the scope"
  - "Skip writing tests"
  - "Deploy without testing in staging"
  - "Change database schema without migration"
  - "Introduce breaking changes to public APIs"

# ALWAYS (common across all types)
always_defaults:
  - "Write tests before or with the fix"
  - "Preserve existing functionality"
  - "Log key state transitions for debugging"
  - "Consider multi-tenant isolation in queries"
  - "Follow project conventions in CLAUDE.md"
  - "Run full test suite before marking as complete"
```

---

## Template Variations

### 1. Bug Fix Template

**Use for**: `product_issue`, `usability_issue` themes

```markdown
## SECTION 2: AI Agent Task Specification

# Agent Task: Fix {{bug_summary}}

## Role & Context

You are a **{{role}}** working in the {{repository}} codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: {{repository}}
**Task Type**: bug-fix
**Related Story**: See Human-Facing Section above
**Priority**: {{priority}} ({{customer_impact}})

## Goal (Single Responsibility)

Fix the bug where {{bug_description}}. The symptoms are: {{symptoms_summary}}. Root cause is suspected to be: {{root_cause_hypothesis}}.

## Context & Architecture

### Relevant Files:

{{#relevant_files}}

- `{{path}}`{{#line_range}} (lines {{line_start}}-{{line_end}}){{/line_range}} - {{relevance}}
  {{/relevant_files}}

### Architecture Notes:

{{architecture_notes}}

### Business Rules:

{{#business_rules}}

- {{.}}
  {{/business_rules}}

### Known Working Behavior:

{{#working_behavior}}

- {{.}}
  {{/working_behavior}}

### Known Failing Behavior:

{{#failing_behavior}}

- {{.}}
  {{/failing_behavior}}

### Related Systems:

{{#related_systems}}

- {{.}}
  {{/related_systems}}

## Instructions (Step-by-Step)

1. **Reproduce** the bug
   - Use the symptoms described in Human-Facing Section
   - Create minimal reproduction case
   - Confirm the exact failure mode

2. **Analyze** the code path
   - Trace execution from trigger to failure point
   - Identify divergence from expected behavior
   - Check logs for error conditions

3. **Identify** root cause
   - Compare working vs failing cases
   - Check for state mismatches, timing issues, or data inconsistencies
   - Validate root cause hypothesis

4. **Implement** the fix
   - Minimal change targeting root cause
   - Maintain backward compatibility
   - Add defensive checks if appropriate

5. **Write regression test**
   - Test case that would fail before fix, passes after
   - Cover edge cases related to the bug
   - Include integration test if bug spans multiple components

6. **Verify** the fix
   - All existing tests pass (no regressions)
   - New test passes
   - Manual verification with reproduction case
   - Test with data matching customer reports

## Success Criteria (Explicit & Observable)

- [ ] Bug is reproducible in test environment
- [ ] Root cause identified and documented
- [ ] Fix applied with minimal code changes
- [ ] Regression test added that fails without fix, passes with fix
- [ ] All existing tests pass (no regressions)
- [ ] Manual verification confirms bug is resolved
- [ ] {{#additional_criteria}}{{.}}{{/additional_criteria}}

## Guardrails & Constraints

### DO NOT:

- Modify code unrelated to the bug
- Skip root cause analysis and jump to fix
- Deploy without reproducing the bug first
- Change behavior of unaffected code paths
- {{#additional_do_not}}{{.}}{{/additional_do_not}}

### ALWAYS:

- Write tests before or with the fix
- Preserve existing functionality
- Log key state transitions for debugging
- Consider multi-tenant isolation in queries
- Document root cause in code comments
- Run full test suite before marking as complete
- {{#additional_always}}{{.}}{{/additional_always}}

## Extended Thinking Guidance

This bug has affected {{customer_count}} customers over {{time_period}}. Consider:

- **Why didn't previous investigations catch it?** - May be timing-dependent, data-dependent, or environment-specific
- **What changed around {{first_reported_date}}?** - When customers first reported issues
- **Could there be multiple root causes?** - Different symptoms may have different triggers
- **Is this a symptom of a deeper issue?** - Look for architectural problems, not just surface bugs

Take time to understand the full failure mode before implementing a fix. A rushed fix may address symptoms without solving the underlying problem.

{{#investigation_queries}}

## Investigation Queries

Use these queries to investigate the issue:

{{#queries}}
\`\`\`sql
-- {{description}}
{{query}}
\`\`\`
{{/queries}}
{{/investigation_queries}}
```

---

### 2. Feature Template

**Use for**: `feature_request` themes

```markdown
## SECTION 2: AI Agent Task Specification

# Agent Task: Implement {{feature_name}}

## Role & Context

You are a **{{role}}** working in the {{repository}} codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: {{repository}}
**Task Type**: feature
**Related Story**: See Human-Facing Section above
**Priority**: {{priority}} ({{customer_demand}})

## Goal (Single Responsibility)

Implement {{feature_description}}. This feature will {{user_benefit}}.

## Context & Architecture

### Relevant Files:

{{#relevant_files}}

- `{{path}}`{{#line_range}} (lines {{line_start}}-{{line_end}}){{/line_range}} - {{relevance}}
  {{/relevant_files}}

### Architecture Notes:

{{architecture_notes}}

### Business Rules:

{{#business_rules}}

- {{.}}
  {{/business_rules}}

### Edge Cases to Consider:

{{#edge_cases}}

- {{.}}
  {{/edge_cases}}

### Integration Points:

{{#integration_points}}

- **{{system}}**: {{interaction}}
  {{/integration_points}}

### Related Systems:

{{#related_systems}}

- {{.}}
  {{/related_systems}}

## Instructions (Step-by-Step)

1. **Design** the implementation
   - Review acceptance criteria in Human-Facing Section
   - Identify integration points with existing code
   - Plan data model changes (if any)
   - Document API contracts (if applicable)

2. **Implement** core functionality
   - Follow existing patterns in the codebase
   - Keep changes scoped to the feature
   - Add logging for key operations
   - Include input validation

3. **Write tests** covering:
   - Happy path: Feature works as expected
   - Edge cases: Boundary conditions, invalid input
   - Integration: Feature interacts correctly with related systems
   - Backward compatibility: Existing functionality unchanged

4. **Add documentation**
   - Code comments for non-obvious logic
   - API documentation (if applicable)
   - Update relevant README or user-facing docs

5. **Verify** completeness
   - All acceptance criteria met
   - Tests pass with good coverage
   - No performance regressions
   - Feature works in realistic scenarios

## Success Criteria (Explicit & Observable)

- [ ] Feature implements all acceptance criteria from Human-Facing Section
- [ ] Happy path works end-to-end
- [ ] Edge cases handled gracefully
- [ ] Tests cover happy path, edge cases, and integrations
- [ ] All existing tests pass (no regressions)
- [ ] Code follows project conventions
- [ ] Documentation added for public APIs
- [ ] {{#additional_criteria}}{{.}}{{/additional_criteria}}

## Guardrails & Constraints

### DO NOT:

- Add features beyond the defined scope
- Modify unrelated code
- Skip edge case handling
- Deploy without integration testing
- Introduce breaking changes to existing APIs
- {{#additional_do_not}}{{.}}{{/additional_do_not}}

### ALWAYS:

- Write tests before or with the implementation
- Follow YAGNI principle (implement only what's specified)
- Validate inputs at API boundaries
- Log feature usage for analytics/debugging
- Consider multi-tenant isolation
- Plan for feature rollback (feature flags if appropriate)
- {{#additional_always}}{{.}}{{/additional_always}}

## Extended Thinking Guidance

This feature was requested by {{customer_count}} customers. Consider:

- **Why do customers need this?** - Understand the underlying workflow or pain point
- **What workarounds are they using today?** - Learn from current behavior
- **How will this scale?** - Consider usage patterns and load
- **What could go wrong?** - Think through failure modes and edge cases
- **Is this feature complete or part of a larger initiative?** - Plan for future extensions

Focus on solving the core problem well rather than adding extra features "just in case."

{{#design_alternatives}}

## Design Alternatives Considered

{{#alternatives}}

### {{name}}

**Pros**: {{pros}}
**Cons**: {{cons}}
**Decision**: {{decision_rationale}}

{{/alternatives}}
{{/design_alternatives}}
```

---

### 3. Performance Template

**Use for**: `performance_issue` themes

```markdown
## SECTION 2: AI Agent Task Specification

# Agent Task: Optimize {{performance_area}}

## Role & Context

You are a **{{role}}** working in the {{repository}} codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: {{repository}}
**Task Type**: performance
**Related Story**: See Human-Facing Section above
**Priority**: {{priority}} ({{performance_impact}})

## Goal (Single Responsibility)

Optimize {{performance_description}} to meet the target of {{performance_target}}. Current performance is {{current_performance}}, which causes {{user_impact}}.

## Context & Architecture

### Relevant Files:

{{#relevant_files}}

- `{{path}}`{{#line_range}} (lines {{line_start}}-{{line_end}}){{/line_range}} - {{relevance}}
  {{/relevant_files}}

### Performance Baseline:

{{#baseline_metrics}}

- **{{metric}}**: {{current_value}} (target: {{target_value}})
  {{/baseline_metrics}}

### Architecture Notes:

{{architecture_notes}}

### Known Bottlenecks:

{{#bottlenecks}}

- {{.}}
  {{/bottlenecks}}

### Related Systems:

{{#related_systems}}

- {{.}}
  {{/related_systems}}

## Instructions (Step-by-Step)

1. **Profile** current performance
   - Establish baseline metrics
   - Identify hotspots using profiling tools
   - Measure database query times, network latency, CPU usage
   - Document findings

2. **Analyze** bottlenecks
   - Prioritize by impact (time × frequency)
   - Identify algorithmic inefficiencies
   - Check for N+1 queries, unnecessary computation, blocking I/O

3. **Design** optimization strategy
   - Choose optimizations with best ROI
   - Consider caching, indexing, query optimization, algorithm improvements
   - Plan for measurement and rollback

4. **Implement** optimizations
   - Make one change at a time
   - Measure impact after each change
   - Preserve correctness (no functional changes)

5. **Write performance tests**
   - Benchmark test covering optimized path
   - Assert performance targets are met
   - Prevent future regressions

6. **Verify** improvement
   - Re-profile after optimization
   - Confirm target metrics achieved
   - Ensure no correctness regressions
   - Test under realistic load

## Success Criteria (Explicit & Observable)

- [ ] Performance profiling completed with baseline metrics
- [ ] Bottlenecks identified and prioritized
- [ ] Optimizations implemented targeting top bottlenecks
- [ ] Performance target achieved: {{performance_target}}
- [ ] All existing tests pass (no correctness regressions)
- [ ] Performance test added to prevent future regressions
- [ ] Optimization documented in code comments
- [ ] {{#additional_criteria}}{{.}}{{/additional_criteria}}

## Guardrails & Constraints

### DO NOT:

- Optimize prematurely without profiling
- Change functionality while optimizing
- Introduce complex solutions for marginal gains
- Deploy without benchmarking in production-like environment
- Sacrifice code readability without significant performance gain
- {{#additional_do_not}}{{.}}{{/additional_do_not}}

### ALWAYS:

- Profile before and after optimization
- Measure impact objectively
- Preserve correctness (add tests if needed)
- Document performance-critical code sections
- Consider memory vs speed tradeoffs
- Plan for monitoring in production
- {{#additional_always}}{{.}}{{/additional_always}}

## Extended Thinking Guidance

This performance issue affects {{customer_count}} customers. Consider:

- **What is the acceptable performance target?** - Based on user expectations, not arbitrary numbers
- **Is this a scalability issue or implementation issue?** - May require architectural changes
- **What are the tradeoffs?** - Complexity, memory, maintainability vs speed
- **How will this perform under peak load?** - Test with realistic data volumes

Focus on measuring first, optimizing second. Premature optimization without data leads to complex code with marginal benefit.

{{#profiling_commands}}

## Profiling Commands

\`\`\`bash

# Profile the target operation

{{profiling_command}}
\`\`\`

{{/profiling_commands}}

{{#benchmark_queries}}

## Benchmark Queries

Use these queries to measure baseline and optimized performance:

{{#queries}}
\`\`\`sql
-- {{description}}
-- Baseline: {{baseline_time}}
{{query}}
\`\`\`
{{/queries}}
{{/benchmark_queries}}
```

---

## Variable Reference

### Header Variables

| Variable          | Type   | Description                             | Example                        |
| ----------------- | ------ | --------------------------------------- | ------------------------------ |
| `task_title`      | string | Concise task name                       | "Fix Community Pin Visibility" |
| `role`            | string | Agent role (engineer type)              | "senior backend engineer"      |
| `repository`      | string | Repository name                         | "tailwind-app"                 |
| `task_type`       | enum   | bug-fix, feature, refactor, performance | "bug-fix"                      |
| `priority`        | enum   | High, Medium, Low                       | "High"                         |
| `priority_reason` | string | Why this priority level                 | "3 customer reports"           |

### Goal Variables

| Variable           | Type   | Description                    | Example                                         |
| ------------------ | ------ | ------------------------------ | ----------------------------------------------- |
| `goal_description` | string | Single-sentence goal statement | "Ensure pins appear in Yours tab after publish" |

### Context Variables

| Variable             | Type         | Description                    | Example                             |
| -------------------- | ------------ | ------------------------------ | ----------------------------------- |
| `relevant_files`     | array        | List of files relevant to task | See structure below                 |
| `code_snippets`      | array        | Code examples with context     | See structure below                 |
| `architecture_notes` | string/array | Architecture context           | "Pin publishing creates records..." |
| `business_rules`     | array        | Domain rules agent must follow | "Pins must appear within 5 min"     |
| `related_systems`    | array        | External systems or components | "Pinterest API (publishing)"        |

#### `relevant_files` Structure

```yaml
path: "src/tailwind_communities/views.py"
line_range:
  line_start: 45
  line_end: 78
relevance: "Queries tribe_content_documents for Yours tab"
```

#### `code_snippets` Structure

```yaml
context: "Current Yours tab query logic"
language: "python"
content: |
  def get_yours_tab_content(user_id):
      return TribeContent.objects.filter(...)
file_path: "src/tailwind_communities/views.py"
line_start: 45
line_end: 52
```

### Instructions Variables

| Variable       | Type  | Description                    | Example             |
| -------------- | ----- | ------------------------------ | ------------------- |
| `instructions` | array | Step-by-step task instructions | See structure below |

#### `instructions` Structure

```yaml
index: 1
title: "Analyze"
description: |
  Trace the query from API endpoint to database.
  Identify any filters that might exclude valid records.
```

### Success Criteria Variables

| Variable           | Type  | Description                    | Example                                  |
| ------------------ | ----- | ------------------------------ | ---------------------------------------- |
| `success_criteria` | array | Observable completion criteria | "Pins appear in Yours tab after publish" |

### Guardrails Variables

| Variable | Type  | Description            | Example                  |
| -------- | ----- | ---------------------- | ------------------------ |
| `do_not` | array | Anti-patterns to avoid | "Modify unrelated code"  |
| `always` | array | Required practices     | "Write tests before fix" |

### Optional Sections

| Variable                | Type   | Description                | Example                            |
| ----------------------- | ------ | -------------------------- | ---------------------------------- |
| `extended_thinking`     | string | Complex reasoning guidance | "Consider multiple root causes..." |
| `investigation_queries` | object | SQL/debugging queries      | See structure below                |

#### `investigation_queries` Structure

```yaml
queries:
  - description: "Check for missing records"
    query: |
      SELECT * FROM tribe_content_documents
      WHERE user_id = ? AND created_at > '2025-11-01'
```

---

## Usage Guidelines

### 1. Selecting Template Variation

| Theme Type          | Template    | Key Sections                           |
| ------------------- | ----------- | -------------------------------------- |
| `product_issue`     | Bug Fix     | Reproduce → Analyze → Identify → Fix   |
| `feature_request`   | Feature     | Design → Implement → Test → Document   |
| `performance_issue` | Performance | Profile → Analyze → Optimize → Verify  |
| `usability_issue`   | Bug Fix     | (Use bug fix template)                 |
| `security_issue`    | Bug Fix     | (Use bug fix with security guardrails) |

### 2. Determining Role

```python
def determine_role(theme_component, theme_type):
    if theme_component in ["tailwind_communities", "pin_scheduler", "tribes"]:
        return "senior backend engineer"
    elif theme_component in ["dashboard", "ui_components", "frontend"]:
        return "senior frontend engineer"
    elif theme_type == "performance_issue":
        return "senior backend engineer" # Most performance issues are backend
    else:
        return "senior fullstack engineer"
```

### 3. Populating Relevant Files

**Priority order:**

1. Files directly implementing the broken/requested functionality
2. Files calling or being called by target files
3. Configuration or schema files affecting the feature
4. Test files covering related functionality

**Limit**: 5-7 most relevant files. Link to broader context if needed.

### 4. Writing Effective Instructions

**Structure:**

- 4-6 steps maximum
- Each step: `Title` (verb) + `Description` (what to do)
- Order: Analyze → Implement → Test → Verify
- Include both what and why

**Examples:**

❌ Bad:

```markdown
1. Fix the bug
2. Test it
3. Deploy
```

✅ Good:

```markdown
1. **Reproduce** the bug
   - Use the symptoms described in Human-Facing Section
   - Create minimal reproduction case
   - Confirm the exact failure mode

2. **Identify** root cause
   - Compare working vs failing cases
   - Check for state mismatches or timing issues
   - Validate root cause hypothesis

3. **Write regression test**
   - Test case that fails before fix, passes after
   - Cover edge cases related to the bug
```

### 5. Crafting Success Criteria

**Requirements:**

- Observable (can be verified)
- Specific (not vague)
- Testable (can be confirmed)
- Includes both functional and quality criteria

**Examples:**

❌ Bad:

```markdown
- [ ] Feature works well
- [ ] Code is good quality
- [ ] Tests are written
```

✅ Good:

```markdown
- [ ] Pins with community assignments appear in Yours tab within 5 minutes
- [ ] All existing tests pass (no regressions)
- [ ] New integration test covers publish → visibility flow
- [ ] Query performance < 100ms for typical user (verified with profiling)
```

### 6. Setting Effective Guardrails

**DO NOT** guardrails:

- Prevent scope creep
- Protect working code
- Enforce process (testing, staging)

**ALWAYS** guardrails:

- Enforce quality standards
- Require testing
- Ensure observability

**Balance:**

- 4-6 DO NOTs (prevent bad actions)
- 4-6 ALWAYS (require good practices)
- Add task-specific items beyond defaults

---

## Example Population Flow

### Input: Theme Object

```json
{
  "issue_signature": "community_pins_not_appearing_in_yours_tab",
  "theme_type": "product_issue",
  "component": "tailwind_communities",
  "occurrences": 3,
  "first_seen": "2025-12-24",
  "last_seen": "2026-01-12",
  "symptoms": [
    "Pins publish successfully",
    "Pins don't appear in Yours tab",
    "DB records exist"
  ],
  "root_cause_hypothesis": "Sync issue between publishing and community visibility"
}
```

### Output: Populated Template

```markdown
## SECTION 2: AI Agent Task Specification

# Agent Task: Fix Community Pin Visibility in Yours Tab

## Role & Context

You are a **senior backend engineer** working in the tailwind-app codebase.
Follow project conventions in `CLAUDE.md` and established patterns.

**Repository**: tailwind-app
**Task Type**: bug-fix
**Related Story**: See Human-Facing Section above
**Priority**: High (3 customer reports, ongoing for 2+ months)

## Goal (Single Responsibility)

Ensure that pins scheduled with community assignments appear in the Communities "Yours" tab after publishing to Pinterest. The data is being written correctly to `tribe_content_documents` - the fix is in the retrieval/display layer.

[... rest of template populated with theme-specific data ...]
```

---

## Validation Checklist

Before finalizing an AI section, verify:

- [ ] **Role** matches component and task type
- [ ] **Goal** is single-responsibility (one clear objective)
- [ ] **Relevant Files** lists 3-7 most important files
- [ ] **Instructions** are 4-6 steps, ordered logically
- [ ] **Success Criteria** are observable and specific
- [ ] **Guardrails** include defaults + task-specific items
- [ ] **Extended Thinking** addresses complexity/ambiguity
- [ ] All variables resolved (no `{{unresolved}}` placeholders)
- [ ] Template variation matches theme type

---

## Integration with Story Generator

### Phase 1: Template Selection

```python
def select_template(theme: Theme) -> str:
    if theme.theme_type == "product_issue":
        return "bug_fix_template"
    elif theme.theme_type == "feature_request":
        return "feature_template"
    elif theme.theme_type == "performance_issue":
        return "performance_template"
    else:
        return "base_template"
```

### Phase 2: Variable Population

```python
def populate_template(template: str, theme: Theme, context: Dict) -> str:
    variables = {
        "task_title": extract_task_title(theme),
        "role": determine_role(theme.component, theme.theme_type),
        "repository": context["repository"],
        "task_type": map_task_type(theme.theme_type),
        "priority": calculate_priority(theme.occurrences),
        "goal_description": generate_goal(theme),
        "relevant_files": extract_relevant_files(theme, context),
        # ... more variables
    }
    return render_template(template, variables)
```

### Phase 3: Validation

```python
def validate_ai_section(section: str) -> List[str]:
    """Returns list of validation errors, empty if valid."""
    errors = []

    if "{{" in section and "}}" in section:
        errors.append("Unresolved template variables found")

    if section.count("## Goal") != 1:
        errors.append("Must have exactly one Goal section")

    if section.count("- [ ]") < 3:
        errors.append("Need at least 3 success criteria")

    # ... more validation rules

    return errors
```

---

## References

- **Example**: `/docs/examples/dual-format-story-example.md` - Full dual-format story
- **Parent Issue**: GitHub #37 - Dual-Format Story Output with Agent SDK Codebase Context
- **Related**: Phase 3.2 Implementation Plan
- **INVEST Standard**: `/docs/story-granularity-standard.md` - Story sizing criteria

---

## Revision History

| Version | Date       | Changes                  | Author        |
| ------- | ---------- | ------------------------ | ------------- |
| 1.0     | 2026-01-15 | Initial template created | Theo (via CC) |

---

_This template is part of the FeedForward dual-format story output system. It ensures AI agents receive structured, actionable task specifications with appropriate context and guardrails._
