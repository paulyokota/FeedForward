#!/bin/bash
# Format voice-mode MCP tool output for better readability
# This hook runs after mcp__voice-mode__converse completes
# It echoes a nicely formatted version of the voice response

# Read the hook input from stdin
input=$(cat)

# Extract the tool response
tool_response=$(echo "$input" | jq -r '.tool_response // empty' 2>/dev/null)

# Skip if no response
if [ -z "$tool_response" ]; then
    exit 0
fi

# Try to parse the voice response result
result=$(echo "$tool_response" | jq -r '.result // empty' 2>/dev/null)

if [ -n "$result" ]; then
    # Extract just the voice response text
    # Handle both "Voice response: ..." and "✓ Message spoken..." formats
    voice_text=$(echo "$result" | sed 's/Voice response: //' | sed 's/ (STT:.*//' | sed 's/✓ //')

    if [ -n "$voice_text" ]; then
        # Print a nicely formatted version
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "🎤 Voice Response:"
        echo ""
        # Word wrap at 60 characters for better readability
        echo "$voice_text" | fold -s -w 60
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    fi
fi

exit 0
