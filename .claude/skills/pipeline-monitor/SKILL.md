---
name: pipeline-monitor
triggers:
  slash_command: /pipeline-monitor
dependencies:
  tools:
    - Task
    - Bash
    - Read
---

# Pipeline Monitor Skill

Spawns a lightweight Haiku agent to monitor a running pipeline in the background. Alerts only when something goes wrong.

## When to Use

Invoke `/pipeline-monitor [run_id]` when:

- A pipeline run is in progress and you want hands-off monitoring
- You want to continue other work while the pipeline runs
- You need to be alerted if the pipeline fails or gets stuck

## Usage

```
/pipeline-monitor 86
```

Or without a run ID (auto-detects active run):

```
/pipeline-monitor
```

## What the Monitor Does

1. **Checks every 60 seconds** for:
   - Fetch progress (conversations fetched count)
   - Phase transitions (classification → embedding → themes → stories)
   - Error messages or failure status
   - Stuck detection (no progress for 5+ minutes)

2. **Output behavior**:
   - Normal: One-line status every 2 minutes (e.g., `[09:05] OK - 1700 fetched, classification`)
   - Alert: `ALERT: [details]` with stack trace from `/tmp/feedforward-app.log`
   - Complete: Final stats summary
   - Failed: Error details and log excerpt

3. **Runs until** pipeline status is `completed` or `failed`

## Implementation

When invoked, Claude spawns a Haiku agent with this prompt:

```
You are monitoring FeedForward pipeline Run {run_id}.

## Check Commands (run every 60s):

1. Fetch progress:
   grep "Fetched" {output_file} | tail -1

2. Current status:
   grep "status=" {output_file} | tail -1

3. Check for errors:
   grep -i "error\|failed\|broken pipe" {output_file} | tail -3

4. DB status (if needed):
   psql "postgresql://localhost:5432/feedforward" -c \
     "SELECT status, current_phase, conversations_classified, themes_extracted, stories_created FROM pipeline_runs WHERE id = {run_id};"

## Output Rules:
- Normal: "[HH:MM] OK - {count} fetched, {phase} phase"
- Error: "ALERT: {error}" then check /tmp/feedforward-app.log
- Complete: "COMPLETE: {convos} classified, {themes} themes, {stories} stories"
- Failed: "FAILED: {error}" with log excerpt

## Loop:
sleep 60 between checks. Stop when status = completed or failed.
```

## Files Monitored

| File                                             | Purpose                       |
| ------------------------------------------------ | ----------------------------- |
| `/private/tmp/claude/.../tasks/{task_id}.output` | Pipeline script stdout        |
| `/tmp/feedforward-app.log`                       | Server logs with stack traces |

## Example Output

```
[09:00] OK - 500 fetched, classification phase
[09:02] OK - 1200 fetched, classification phase
[09:04] OK - 1763 fetched, embedding_generation phase
[09:06] OK - embedding complete, theme_extraction phase
[09:08] OK - 145 themes, story_creation phase
[09:10] COMPLETE: 1763 classified, 145 themes, 12 stories, 89 orphans
```

Or on failure:

```
[09:05] ALERT: Pipeline failed with [Errno 32] Broken pipe
Stack trace from /tmp/feedforward-app.log:
  File "src/classification_pipeline.py", line 464, in run_pipeline_async
    print(f"\n{'='*60}")
BrokenPipeError: [Errno 32] Broken pipe
```

## Integration with dev-pipeline-run.sh

The monitor complements `dev-pipeline-run.sh`:

1. Start pipeline: `./scripts/dev-pipeline-run.sh --days 45`
2. When it backgrounds, invoke: `/pipeline-monitor`
3. Continue with other work
4. Get alerted only if something breaks
