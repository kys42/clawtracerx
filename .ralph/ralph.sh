#!/bin/bash
# Ralph Loop Runner — ClawTracerX (infinite mode)
# Usage: .ralph/ralph.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

ITER=0

echo "=== Ralph Loop Starting (infinite mode) ==="
echo "Project: $PROJECT_DIR"
echo "PRD: .ralph/prd.json"
echo "Stop: Ctrl+C"
echo ""

while true; do
  ITER=$((ITER + 1))

  echo ""
  echo "=========================================="
  echo "  Ralph Loop $ITER"
  echo "  $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=========================================="
  echo ""

  REMAINING=$(cat .ralph/prd.json | jq '[.userStories[] | select(.passes == false)] | length')
  echo "Remaining stories: $REMAINING (auto-generates more when 0)"

  # Run Claude Code with the prompt
  claude --print "$(cat .ralph/PROMPT.md)" \
    --allowedTools "Write,Read,Edit,Glob,Grep,Bash(pip *),Bash(pytest *),Bash(ruff *),Bash(git add *),Bash(git commit *),Bash(git status),Bash(git diff *),Bash(ctrace *),Bash(python *),Bash(cat *),Bash(ls *),Bash(wc *)"

  EXIT_CODE=$?
  echo "Loop $ITER exit code: $EXIT_CODE"

  DONE=$(cat .ralph/prd.json | jq '[.userStories[] | select(.passes == true)] | length')
  TOTAL=$(cat .ralph/prd.json | jq '[.userStories[]] | length')
  echo "Stories: $DONE / $TOTAL complete"

  sleep 2
done
