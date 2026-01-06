#!/bin/bash
# Hook to block direct pushes to main branch
# This enforces the branch workflow: always use feature branches and PRs

BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

if [[ "$BRANCH" == "main" || "$BRANCH" == "master" ]]; then
  echo "ERROR: Cannot push directly to $BRANCH branch!"
  echo "Please use a feature branch and create a PR instead."
  echo "See CLAUDE.md Development Constraints for branch workflow."
  exit 1
fi

# Check if trying to push TO main (regardless of current branch)
if [[ "$*" == *"origin main"* || "$*" == *"origin master"* ]]; then
  echo "ERROR: Cannot push directly to main/master!"
  echo "Please create a PR instead."
  exit 1
fi

exit 0
