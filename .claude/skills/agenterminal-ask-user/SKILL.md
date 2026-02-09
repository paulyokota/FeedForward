---
name: agenterminal-ask-user
description: Use when you need to ask the user a question with selectable options while running in an AgenTerminal headless session. Routes questions through the AgenTerminal UI instead of the failing built-in AskUserQuestion tool.
---

# Agenterminal Ask User

Use this when you need to ask the user a question with predefined options while running in AgenTerminal headless mode.

**IMPORTANT:** In AgenTerminal sessions, the built-in AskUserQuestion tool does not work because there is no interactive terminal. Use `agenterminal.ask` instead.

## Usage

Call the `agenterminal.ask` MCP tool:

```
agenterminal.ask
questions:
  - question: "Which approach should we use?"
    header: "Approach"
    options:
      - label: "Option A"
        description: "Fast but less thorough"
      - label: "Option B"
        description: "Thorough but slower"
    multiSelect: false
```

## Parameters

- `questions` (required): Array of question objects, each with:
  - `question` (required): The question text
  - `header` (optional): Short header label shown above the question
  - `options` (required): Array of options, each with `label` (required) and `description` (optional)
  - `multiSelect` (optional, default false): If true, user can select multiple options

## Response

The tool blocks until the user responds (up to 5 minutes). Returns:

```json
{
  "answers": [
    {
      "question": "Which approach should we use?",
      "selected": ["Option A"]
    }
  ]
}
```

If the user does not respond, returns:

```json
{
  "error": "timeout",
  "message": "User did not respond within 5 minutes."
}
```

## Tips

- Keep options concise but descriptive.
- Use `header` to group related questions visually.
- Use `multiSelect: true` only when multiple selections genuinely make sense.
- You can ask multiple questions in a single call; the user answers all of them before submitting.
