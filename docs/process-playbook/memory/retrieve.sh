#!/bin/bash
# Agent memory retrieval script
# Usage: ./retrieve.sh <agent> <keywords...>
# Example: ./retrieve.sh backend schema migration

set -e

AGENT=$1
shift
KEYWORDS="$@"

# Find the memory directory (support both .claude/memory and process-playbook/memory)
if [ -d ".claude/memory/$AGENT" ]; then
  MEMORY_DIR=".claude/memory/$AGENT"
elif [ -d "process-playbook/memory/$AGENT" ]; then
  MEMORY_DIR="process-playbook/memory/$AGENT"
else
  echo "No memories found for agent: $AGENT"
  echo "Checked: .claude/memory/$AGENT, process-playbook/memory/$AGENT"
  exit 0
fi

# Build grep pattern from keywords
PATTERN=$(echo "$KEYWORDS" | tr ' ' '|')

echo "## Relevant Past Experiences for $AGENT"
echo ""

# Find matching files
FILES=$(grep -l -i -E "$PATTERN" "$MEMORY_DIR"/*.md 2>/dev/null | head -5)

if [ -z "$FILES" ]; then
  echo "No matching memories found for keywords: $KEYWORDS"
  exit 0
fi

for file in $FILES; do
  # Extract frontmatter fields
  DATE=$(grep "^date:" "$file" 2>/dev/null | cut -d' ' -f2 || echo "unknown")
  PR=$(grep "^pr:" "$file" 2>/dev/null | cut -d' ' -f2 || echo "N/A")
  IMPACT=$(grep "^impact:" "$file" 2>/dev/null | cut -d' ' -f2 || echo "unknown")
  TYPE=$(grep "^type:" "$file" 2>/dev/null | cut -d' ' -f2 || echo "unknown")

  # Get a title from the filename or first heading
  FILENAME=$(basename "$file" .md)
  TITLE=$(grep "^## " "$file" 2>/dev/null | head -1 | sed 's/^## //' || echo "$FILENAME")

  echo "### PR #$PR - $TITLE ($DATE)"
  echo "**Type**: $TYPE | **Impact**: $IMPACT"
  echo ""

  # Extract lesson section (most important part)
  if grep -q "^## Lesson" "$file" 2>/dev/null; then
    sed -n '/^## Lesson/,/^## /p' "$file" | grep -v "^##" | sed '/^$/d' | head -10
  else
    # Fallback: show first meaningful content
    grep -v "^---" "$file" | grep -v "^[a-z]*:" | head -10
  fi

  echo ""
  echo "---"
  echo ""
done

echo "Retrieved $(echo "$FILES" | wc -w | tr -d ' ') memories for $AGENT"
