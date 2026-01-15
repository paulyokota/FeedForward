---
name: voice
triggers:
  keywords:
    - voice mode
    - start voice
    - voice chat
    - talk to me
    - let's talk
    - voice conversation
dependencies:
  tools:
    - mcp__voice-mode__converse
---

# Voice Mode Skill

Start a voice conversation with relaxed silence detection settings.

## Purpose

Quickly start voice mode with sensible defaults that work well for natural conversation, avoiding premature cutoffs from aggressive silence detection.

## Usage

Invoke with `/voice` or `/voice [message]`

### Examples

```
/voice                          # Start listening for voice input
/voice Hello, what's on your mind?  # Speak a message and listen
```

## Default Settings

| Setting               | Value     | Reason                                              |
| --------------------- | --------- | --------------------------------------------------- |
| `vad_aggressiveness`  | 0         | Least aggressive - won't cut off speech prematurely |
| `listen_duration_min` | 4         | Wait at least 4 seconds before considering silence  |
| `listen_duration_max` | 120       | Allow up to 2 minutes of speaking                   |
| `wait_for_response`   | true      | Listen for user response after speaking             |
| `metrics_level`       | "minimal" | Clean output - just response text, saves tokens     |

## Workflow

### Starting Voice Mode

1. **If no message provided**: Start listening immediately with a friendly prompt
2. **If message provided**: Speak the message, then listen for response

### Continuing Conversation

- Continue using the `mcp__voice-mode__converse` tool with the same settings
- Each response loops back to listening mode
- Conversation continues until user says "stop" or "end voice mode"

### Ending Voice Mode

User can say:

- "Stop voice mode"
- "End voice"
- "Switch to text"
- "That's all for now"

When ending, acknowledge and return to text-based interaction.

## Implementation

When this skill is invoked, use these tool parameters:

```python
mcp__voice-mode__converse(
    message="[user message or greeting]",
    wait_for_response=True,
    vad_aggressiveness=0,
    listen_duration_min=4,
    listen_duration_max=120,
    metrics_level="minimal",
)
```

### Multi-Sentence Responses (Preferred)

For longer responses, **break them into multiple sequential tool calls**. This provides better readability and a more natural conversation flow:

```python
# For multi-sentence responses, queue them up like this:
mcp__voice-mode__converse(message="First sentence.", wait_for_response=False, ...)
mcp__voice-mode__converse(message="Second sentence.", wait_for_response=False, ...)
mcp__voice-mode__converse(message="Final sentence. Now listening.", wait_for_response=True, ...)
```

**Guidelines:**

- Set `wait_for_response=False` for all messages except the last one
- Only the final message should have `wait_for_response=True`
- Keep each message to 1-2 sentences for natural pacing
- Queue all messages in a single tool call block so they play sequentially

## Adjusting Settings

Users can request adjustments:

- "Be more aggressive with silence detection" → `vad_aggressiveness=2`
- "Listen longer before cutting off" → `listen_duration_min=6`
- "Quick responses only" → `listen_duration_max=30`

## Troubleshooting

### Voice not being detected

- Check microphone permissions
- Try `mcp__voice-mode__service("whisper", "status")` to verify STT service

### Speech being cut off early

- Lower `vad_aggressiveness` to 0
- Increase `listen_duration_min`

### Service not running

```python
mcp__voice-mode__service("whisper", "start")
mcp__voice-mode__service("kokoro", "start")
```

## Key MCP Resources

- `voicemode://docs/quickstart` - Basic usage
- `voicemode://docs/parameters` - Full parameter reference
- `voicemode://docs/troubleshooting` - Common issues

## Notes

- Voice mode works best in quiet environments
- Responses are transcribed via Whisper STT
- TTS uses Kokoro or OpenAI depending on configuration
