---
description: Start voice conversation with relaxed silence detection
argument-hint: [optional greeting message]
---

# Voice Mode

Start a voice conversation with settings optimized for natural speech.

## Default Settings

- **VAD Aggressiveness**: 0 (least aggressive - won't cut off speech prematurely)
- **Min Listen Duration**: 4 seconds (wait before considering silence)
- **Max Listen Duration**: 120 seconds (2 minutes of speaking allowed)
- **Wait for Response**: true (listen after speaking)

## Usage

Start voice mode with these parameters:

```python
mcp__voice-mode__converse(
    message="$ARGUMENTS" if "$ARGUMENTS" else "I'm listening. What would you like to discuss?",
    wait_for_response=True,
    vad_aggressiveness=0,
    listen_duration_min=4,
    listen_duration_max=120,
)
```

## Continuing the Conversation

After receiving voice input, continue using the same tool with the same settings. The conversation loops naturally until the user says:

- "Stop voice mode"
- "End voice"
- "Switch to text"
- "That's all"

When ending, acknowledge and return to text-based interaction.

## Adjusting Settings Mid-Conversation

Users can request adjustments by voice:

- "Be more aggressive with silence detection" → increase `vad_aggressiveness`
- "Listen longer before cutting off" → increase `listen_duration_min`
- "Quick responses only" → decrease `listen_duration_max`

## Troubleshooting

If voice services aren't running:

```python
mcp__voice-mode__service("whisper", "start")  # STT
mcp__voice-mode__service("kokoro", "start")   # TTS
```

Check service status:

```python
mcp__voice-mode__service("whisper", "status")
mcp__voice-mode__service("kokoro", "status")
```
