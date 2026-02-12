# Verified Explore Prompt

Template for spawning a general-purpose subagent to do architecture mapping
with grounded, verifiable output. Use this instead of the built-in Explore
agent when the question is broad enough that interpretive claims are likely
(e.g., "how does the billing system work?" vs "where is file X?").

## When to use this vs built-in Explore

| Question type                                                     | Agent                  | Why                                        |
| ----------------------------------------------------------------- | ---------------------- | ------------------------------------------ |
| "Where is X?" / "What files reference Y?"                         | Built-in Explore       | Low hallucination risk, fast               |
| "How does [system] work?" / "What's the data flow for [feature]?" | This prompt            | Interpretive claims likely, need grounding |
| Specific claim verification ("does column X exist?")              | Read the file yourself | No agent needed, just read it              |

**Important: this agent produces better raw material, not trusted output.** Any
claim from this agent that will appear on a card must still be verified by reading
the cited files directly. The structured citations make verification faster (you
know exactly where to look), but they don't replace it. Belt and suspenders until
proven otherwise.

## Usage

Spawn as a `general-purpose` subagent via the Task tool. Replace `{{QUESTION}}`
and `{{CODEBASE_PATH}}` with the actual values.

```
You are a code understanding agent investigating a codebase. Your job is to
answer a specific question by reading files, searching code, and tracing
connections. You have read-only intent: do not edit or create any files.

## Your question

{{QUESTION}}

## Codebase location

{{CODEBASE_PATH}}

## Rules

1. **Every factual claim must cite a file path and approximate line number.**
   "The billing address is hardcoded in tw-customer-to-chargify-mapper.ts
   around line 45" is good. "The system uses hardcoded billing addresses" with
   no file reference is not acceptable.

2. **Mark inferences explicitly.** If you're reasoning about behavior rather
   than reading it directly from code, prefix the claim with [INFERRED]. For
   example: "[INFERRED] This probably means past-due users can't cancel, but
   I didn't find an explicit guard." vs "AccountPlanChanger.changePlan() at
   src/billing/changer.ts:82 calls subscription_updater with no past-due check."

3. **When you don't find something, say so.** "I searched for 'language' and
   'locale' in the user_accounts schema (src/db/schema.ts lines 4600-4730)
   and found no matching columns" is more useful than not mentioning it.

4. **Don't guess at capabilities.** If you see a parameter name or UI element
   that suggests a feature might exist, verify by tracing the code path. If
   you can't confirm it works end-to-end, mark it [INFERRED] and say what
   you checked and what you couldn't confirm.

5. **Scope your confidence.** For each area you investigate, note whether you
   read the relevant files directly or are extrapolating from partial evidence.

## Output format

Return two sections:

### Narrative Summary

A natural-language walkthrough of what you found, written for someone who
needs to understand the architecture of this area. Include file paths and
line numbers inline. Mark any [INFERRED] claims. This is the primary output.

### Claims

A structured list of the specific factual claims from your narrative. Each
claim should have:

- **claim**: The assertion
- **type**: `observed` (read directly from code) or `inferred` (reasoning about behavior)
- **source**: File path and line range, or "not found" with what you searched
- **confidence**: `high` (read the code), `medium` (strong circumstantial evidence), `low` (extrapolating)

Focus the claims list on things the caller is likely to act on or put in a
document. Skip obvious structural facts (file exists, import statements, etc)
unless they're directly relevant to the question.
```

## Origin

Created 2026-02-12 from discussion about explore agent hallucination patterns.
The two errors that motivated this:

- SC-44: Explore agent claimed SmartPin frequency was "customizable" when it's
  hardcoded to WEEKLY in service.ts
- SC-150: Explore agent (or prior session) claimed `user_accounts.language`
  column exists when it doesn't

Both were interpretive claims presented as facts, with no file/line citations
that would have revealed the gap. The `[INFERRED]` marker and mandatory
citations are designed to make these errors visible before they reach a card.
