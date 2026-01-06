#!/bin/bash
# Hook to verify tests passed after running them
# If tests fail, this signals Claude to fix them before proceeding

# Check the exit code from the test run
# This hook runs AFTER the test command, so we check if it succeeded

# The test command's exit code is passed to this script
TEST_EXIT_CODE=${1:-0}

if [[ "$TEST_EXIT_CODE" -ne 0 ]]; then
  echo "WARNING: Tests failed!"
  echo "Please review the test output and fix failing tests before continuing."
  # Exit 1 to signal the hook failed, which tells Claude to address the issue
  exit 1
fi

echo "Tests passed successfully."
exit 0
