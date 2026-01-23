#!/bin/bash
# Dev Mode Pipeline Runner
#
# This script ensures safe pipeline execution during development:
# 1. Pre-flight checks (server running, no active runs, current code)
# 2. Auto-cleanup of stale data
# 3. Triggers full pipeline via API
# 4. Monitors progress until completion
#
# Usage: ./scripts/dev-pipeline-run.sh [--skip-cleanup] [--days N]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

API_URL="http://localhost:8000"
SKIP_CLEANUP=false
DAYS=3

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-cleanup)
            SKIP_CLEANUP=true
            shift
            ;;
        --days)
            DAYS="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--skip-cleanup] [--days N]"
            echo ""
            echo "Options:"
            echo "  --skip-cleanup  Skip the auto-cleanup step (NOT recommended in dev mode)"
            echo "  --days N        Number of days of conversations to process (default: 3)"
            echo ""
            echo "This script runs the FULL pipeline (classification → embedding → themes → stories)"
            echo "with safety checks and auto-cleanup for development iteration."
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  DEV MODE PIPELINE RUNNER${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# ============================================
# PRE-FLIGHT CHECK 1: Server Running?
# ============================================
echo -e "${YELLOW}[1/5] Checking if API server is running...${NC}"

if ! curl -s "$API_URL/api/pipeline/active" > /dev/null 2>&1; then
    echo -e "${RED}ERROR: API server not responding at $API_URL${NC}"
    echo -e "${RED}Start it with: uvicorn src.api.main:app --reload --port 8000${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Server is running${NC}"

# ============================================
# PRE-FLIGHT CHECK 2: Active Run?
# ============================================
echo -e "${YELLOW}[2/5] Checking for active pipeline runs...${NC}"

ACTIVE_RUN=$(curl -s "$API_URL/api/pipeline/active" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('run_id', 'none') if d.get('active') else 'none')")

if [ "$ACTIVE_RUN" != "none" ]; then
    echo -e "${RED}ERROR: Pipeline run $ACTIVE_RUN is already in progress${NC}"
    echo -e "${RED}Wait for it to complete or stop it first${NC}"
    exit 1
fi
echo -e "${GREEN}✓ No active pipeline runs${NC}"

# ============================================
# PRE-FLIGHT CHECK 3: Server Has Current Code?
# ============================================
echo -e "${YELLOW}[3/5] Checking if server has current code...${NC}"

# Get last commit timestamp
LAST_COMMIT=$(git log -1 --format=%ct 2>/dev/null || echo "0")
LAST_COMMIT_MSG=$(git log -1 --format=%s 2>/dev/null || echo "unknown")

# Get server process start time (approximate via PID creation time)
SERVER_PID=$(pgrep -f "uvicorn src.api.main:app" | head -1 || echo "")

if [ -z "$SERVER_PID" ]; then
    echo -e "${YELLOW}No server running. Starting one...${NC}"
    uvicorn src.api.main:app --reload --port 8000 &
    STARTED_SERVER=true
    sleep 5

    # Verify it started
    if ! curl -s "$API_URL/api/pipeline/active" > /dev/null 2>&1; then
        echo -e "${RED}ERROR: Failed to start server${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ Server started${NC}"
else
    STARTED_SERVER=false

    # On macOS, get process start time
    if [[ "$OSTYPE" == "darwin"* ]]; then
        SERVER_START=$(ps -p "$SERVER_PID" -o lstart= | xargs -I{} date -j -f "%a %b %d %T %Y" "{}" "+%s" 2>/dev/null || echo "0")
    else
        SERVER_START=$(stat -c %Y /proc/"$SERVER_PID" 2>/dev/null || echo "0")
    fi

    if [ "$LAST_COMMIT" -gt "$SERVER_START" ] 2>/dev/null; then
        echo -e "${YELLOW}Code changed after server started. Auto-restarting...${NC}"
        echo -e "${YELLOW}Last commit: $LAST_COMMIT_MSG${NC}"

        # Kill old server
        pkill -f "uvicorn src.api.main:app" 2>/dev/null || true
        sleep 2

        # Start new server
        uvicorn src.api.main:app --reload --port 8000 &
        STARTED_SERVER=true
        sleep 5

        # Verify it started
        if ! curl -s "$API_URL/api/pipeline/active" > /dev/null 2>&1; then
            echo -e "${RED}ERROR: Failed to restart server${NC}"
            exit 1
        fi
        echo -e "${GREEN}✓ Server restarted with current code${NC}"
    else
        echo -e "${GREEN}✓ Server has current code${NC}"
    fi
fi

# ============================================
# PRE-FLIGHT CHECK 4: Uncommitted Changes?
# ============================================
echo -e "${YELLOW}[4/5] Checking for uncommitted changes...${NC}"

if [ -n "$(git status --porcelain src/)" ]; then
    echo -e "${YELLOW}WARNING: Uncommitted changes in src/${NC}"
    git status --short src/
    echo ""
    read -p "Continue with uncommitted changes? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo -e "${GREEN}✓ No uncommitted changes in src/${NC}"
fi

# ============================================
# AUTO-CLEANUP (Dev Mode)
# ============================================
if [ "$SKIP_CLEANUP" = false ]; then
    echo -e "${YELLOW}[5/5] Running dev-mode cleanup...${NC}"

    # Run cleanup via Python
    python3 << 'CLEANUP_SCRIPT'
from src.db.connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        # Delete orphans
        cur.execute("DELETE FROM story_orphans WHERE graduated_at IS NULL")
        orphans_deleted = cur.rowcount

        # Delete stories (cascades to evidence, comments, sync_metadata)
        cur.execute("DELETE FROM stories")
        stories_deleted = cur.rowcount

        # Delete themes
        cur.execute("DELETE FROM themes")
        themes_deleted = cur.rowcount

        # Delete facets (from bad runs)
        cur.execute("DELETE FROM conversation_facets")
        facets_deleted = cur.rowcount

        # Delete embeddings (from bad runs)
        cur.execute("DELETE FROM conversation_embeddings")
        embeddings_deleted = cur.rowcount

        # Unlink conversations from runs
        cur.execute("UPDATE conversations SET pipeline_run_id = NULL")
        convos_unlinked = cur.rowcount

        conn.commit()

        print(f"  Deleted {orphans_deleted} orphans")
        print(f"  Deleted {stories_deleted} stories")
        print(f"  Deleted {themes_deleted} themes")
        print(f"  Deleted {facets_deleted} facets")
        print(f"  Deleted {embeddings_deleted} embeddings")
        print(f"  Unlinked {convos_unlinked} conversations from runs")
CLEANUP_SCRIPT

    echo -e "${GREEN}✓ Cleanup complete${NC}"
else
    echo -e "${YELLOW}[5/5] Skipping cleanup (--skip-cleanup flag)${NC}"
fi

echo ""
echo -e "${BLUE}======================================${NC}"
echo -e "${BLUE}  STARTING PIPELINE RUN${NC}"
echo -e "${BLUE}======================================${NC}"
echo ""

# ============================================
# TRIGGER PIPELINE
# ============================================
RESPONSE=$(curl -s -X POST "$API_URL/api/pipeline/run" \
    -H "Content-Type: application/json" \
    -d "{\"days\": $DAYS, \"auto_create_stories\": true}")

RUN_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('run_id', 'error'))")

if [ "$RUN_ID" = "error" ]; then
    echo -e "${RED}ERROR: Failed to start pipeline${NC}"
    echo "$RESPONSE"
    exit 1
fi

echo -e "${GREEN}Started pipeline run $RUN_ID${NC}"
echo ""

# ============================================
# MONITOR PROGRESS
# ============================================
echo -e "${YELLOW}Monitoring progress (Ctrl+C to stop monitoring, run continues)...${NC}"
echo ""

while true; do
    STATUS=$(curl -s "$API_URL/api/pipeline/status/$RUN_ID")

    PHASE=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('current_phase', '?'))")
    RUN_STATUS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status', '?'))")
    STORIES=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stories_created', 0))")
    ORPHANS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('orphans_created', 0))")
    THEMES=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('themes_extracted', 0))")
    CONVOS=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('conversations_classified', 0))")

    echo -ne "\r[$(date +%H:%M:%S)] status=$RUN_STATUS | phase=$PHASE | convos=$CONVOS | themes=$THEMES | stories=$STORIES | orphans=$ORPHANS    "

    if [ "$RUN_STATUS" = "completed" ] || [ "$RUN_STATUS" = "failed" ]; then
        echo ""
        echo ""

        if [ "$RUN_STATUS" = "completed" ]; then
            echo -e "${GREEN}======================================${NC}"
            echo -e "${GREEN}  PIPELINE COMPLETED SUCCESSFULLY${NC}"
            echo -e "${GREEN}======================================${NC}"
            echo ""
            echo "Results:"
            echo "  - Conversations classified: $CONVOS"
            echo "  - Themes extracted: $THEMES"
            echo "  - Stories created: $STORIES"
            echo "  - Orphans created: $ORPHANS"

            if [ "$STORIES" -eq 0 ] && [ "$ORPHANS" -gt 0 ]; then
                echo ""
                echo -e "${YELLOW}WARNING: No stories created, only orphans.${NC}"
                echo -e "${YELLOW}This may indicate PM review rejected all clusters.${NC}"
            fi
        else
            ERROR=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error_message', 'unknown'))")
            echo -e "${RED}======================================${NC}"
            echo -e "${RED}  PIPELINE FAILED${NC}"
            echo -e "${RED}======================================${NC}"
            echo ""
            echo -e "${RED}Error: $ERROR${NC}"
            exit 1
        fi

        break
    fi

    sleep 5
done

echo ""
echo -e "${BLUE}Run 'curl -s $API_URL/api/pipeline/status/$RUN_ID | python3 -m json.tool' for full details${NC}"
