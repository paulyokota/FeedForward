---
description: End voice conversation and return to text mode
---

# Stop Voice Mode

End the current voice conversation and return to text-based interaction.

## Action

Speak a closing message without listening for a response:

```python
mcp__voice-mode__converse(
    message="Switching back to text mode. You can continue typing your messages.",
    wait_for_response=False,
)
```

Then continue the conversation via text input.

## When to Use

- User types `/voice-stop` during a voice session
- User says "stop voice mode" or similar (detected via voice)
- User wants to switch back to text for complex input

## Notes

This command just stops listening - it doesn't shut down the voice services.
Voice mode can be started again anytime with `/voice`.
