---
name: Feasibility Infeasible Reason Required
about: Enforce non-empty infeasibility_reason for infeasible assessments
title: "Require infeasibility_reason when feasibility_assessment is infeasible"
labels: bug, priority-high, discovery-engine
assignees: ""
---

**Phase**: Discovery Engine | **Priority**: high | **Type**: bug

## Problem

Infeasible solutions sometimes record empty or generic infeasibility reasons,
reducing the usefulness of the backward flow that relies on these constraints.

## Root Cause

Tech Lead prompt allows empty strings in some paths, and the FeasibilityDesigner
does not enforce a non-empty, specific `infeasibility_reason` when
`feasibility_assessment` is infeasible.

## Impact

- Infeasible solutions lack actionable rationale
- Stage 2 cannot design around specific constraints
- Human review loses context on why an idea was rejected

## Tasks

- [ ] Update Tech Lead prompt to require a specific reason when infeasible
- [ ] Add validation in FeasibilityDesigner: if infeasible and reason empty or
      placeholder, log error and retry or fail the round
- [ ] Add test coverage for infeasible path requiring reason

## Evidence

- `src/discovery/agents/prompts.py:1069-1079` — schema allows empty string
- `src/discovery/agents/tech_lead_agent.py:120-200` — `infeasibility_reason` default
- `src/discovery/agents/feasibility_designer.py:1-140` — no explicit enforcement

## Fix Complexity

Low/medium — prompt tweak + validation guard + test
