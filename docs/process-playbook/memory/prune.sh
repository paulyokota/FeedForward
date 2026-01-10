#!/bin/bash
# Memory pruning script
# Usage: ./prune.sh [--dry-run | --execute]
#
# Prunes old, low-impact memory files:
# - impact: low files older than 30 days -> DELETE
# - impact: medium files older than 90 days -> FLAG for review
# - impact: high files -> NEVER delete

set -e

MODE=${1:---dry-run}

# Find memory directory
if [ -d ".claude/memory" ]; then
  MEMORY_DIR=".claude/memory"
elif [ -d "process-playbook/memory" ]; then
  MEMORY_DIR="process-playbook/memory"
else
  echo "No memory directory found."
  exit 1
fi

echo "Memory Pruning Report"
echo "====================="
echo "Directory: $MEMORY_DIR"
echo "Mode: $MODE"
echo ""

# Counters
TO_DELETE=0
TO_REVIEW=0
PRESERVED=0

# Current date for comparison
NOW=$(date +%s)
THIRTY_DAYS=$((30 * 24 * 60 * 60))
NINETY_DAYS=$((90 * 24 * 60 * 60))

echo "## Files to DELETE (impact: low, > 30 days)"
echo ""

# Find all memory files (excluding README)
find "$MEMORY_DIR" -name "*.md" -type f ! -name "README.md" | while read -r file; do
  # Extract impact and date
  IMPACT=$(grep "^impact:" "$file" 2>/dev/null | cut -d' ' -f2 || echo "unknown")
  DATE_STR=$(grep "^date:" "$file" 2>/dev/null | cut -d' ' -f2 || echo "")

  if [ -z "$DATE_STR" ]; then
    continue
  fi

  # Convert date to seconds (macOS compatible)
  FILE_DATE=$(date -j -f "%Y-%m-%d" "$DATE_STR" +%s 2>/dev/null || date -d "$DATE_STR" +%s 2>/dev/null || echo "0")
  AGE=$((NOW - FILE_DATE))
  AGE_DAYS=$((AGE / 86400))

  if [ "$IMPACT" = "low" ] && [ "$AGE" -gt "$THIRTY_DAYS" ]; then
    echo "- $file (age: ${AGE_DAYS} days)"
    ((TO_DELETE++)) || true

    if [ "$MODE" = "--execute" ]; then
      rm "$file"
      echo "  DELETED"
    fi
  elif [ "$IMPACT" = "medium" ] && [ "$AGE" -gt "$NINETY_DAYS" ]; then
    echo ""
    echo "## Files to REVIEW (impact: medium, > 90 days)"
    echo "- $file (age: ${AGE_DAYS} days)"
    ((TO_REVIEW++)) || true
  elif [ "$IMPACT" = "high" ]; then
    ((PRESERVED++)) || true
  fi
done

echo ""
echo "## Summary"
echo ""
echo "- Files to delete (low, > 30 days): $TO_DELETE"
echo "- Files to review (medium, > 90 days): $TO_REVIEW"
echo "- Files preserved (high impact): $PRESERVED"
echo ""

if [ "$MODE" = "--dry-run" ]; then
  echo "Dry run complete. Use --execute to actually delete files."
elif [ "$MODE" = "--execute" ]; then
  echo "Pruning complete. $TO_DELETE files deleted."
fi
