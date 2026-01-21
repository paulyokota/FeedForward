"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import type {
  PipelineStatus,
  PipelineRunListItem,
  PipelineRunRequest,
  Story,
} from "@/lib/types";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import Link from "next/link";

const STATUS_POLL_INTERVAL = 2000; // 2 seconds

type FormState = {
  days: number;
  maxConversations: string;
  dryRun: boolean;
  concurrency: number;
  autoCreateStories: boolean;
};

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "-";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}m ${secs}s`;
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  return date.toLocaleString();
}

function getStatusColor(status: string): string {
  switch (status) {
    case "running":
      return "var(--accent-blue)";
    case "stopping":
      return "var(--accent-amber)";
    case "stopped":
      return "var(--accent-amber)";
    case "completed":
      return "var(--accent-green)";
    case "failed":
      return "var(--accent-red)";
    default:
      return "var(--text-muted)";
  }
}

function getPhaseLabel(phase: string | null): string {
  switch (phase) {
    case "classification":
      return "Classifying...";
    case "theme_extraction":
      return "Extracting themes...";
    case "pm_review":
      return "Running PM review...";
    case "story_creation":
      return "Creating stories...";
    case "completed":
      return "Completed";
    default:
      return "Processing...";
  }
}

export default function PipelinePage() {
  const [activeStatus, setActiveStatus] = useState<PipelineStatus | null>(null);
  const [history, setHistory] = useState<PipelineRunListItem[]>([]);
  const [newStories, setNewStories] = useState<Story[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [selectedRunStatus, setSelectedRunStatus] =
    useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [formState, setFormState] = useState<FormState>({
    days: 7,
    maxConversations: "",
    dryRun: false,
    concurrency: 20,
    autoCreateStories: false,
  });
  const [isCreatingStories, setIsCreatingStories] = useState(false);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  // Track whether user has manually selected a run (prevents auto-selection override)
  const hasUserSelectedRunRef = useRef<boolean>(false);

  // Limit for new stories display - extract as constant for maintainability
  const NEW_STORIES_DISPLAY_LIMIT = 50;

  // Fetch stories created since a specific timestamp
  // Note: This filters by run start time, not run completion time
  const fetchStoriesCreatedSince = useCallback(
    async (sinceTimestamp: string) => {
      try {
        const response = await api.stories.list({
          created_since: sinceTimestamp,
          limit: NEW_STORIES_DISPLAY_LIMIT,
        });
        setNewStories(response.stories);
      } catch (err) {
        console.error("Failed to fetch new stories:", err);
        setNewStories([]);
      }
    },
    [],
  );

  // Check for active run and fetch history
  const fetchData = useCallback(async () => {
    try {
      const [activeResponse, historyResponse] = await Promise.all([
        api.pipeline.active(),
        api.pipeline.history(10),
      ]);

      if (activeResponse.active && activeResponse.run_id) {
        const status = await api.pipeline.status(activeResponse.run_id);
        setActiveStatus(status);
      } else {
        setActiveStatus(null);
      }

      setHistory(historyResponse);

      // Auto-select the most recent completed run to show its new stories.
      // Only auto-select if:
      // 1. User hasn't manually clicked a run yet (hasUserSelectedRunRef)
      // 2. There are completed runs with valid timestamps
      // This prevents the UI from overriding user selection during polling refreshes.
      if (!hasUserSelectedRunRef.current) {
        const completedRuns = historyResponse.filter(
          (run) => run.status === "completed" && run.started_at,
        );
        if (completedRuns.length > 0) {
          const latestRun = completedRuns[0];
          setSelectedRunId(latestRun.id);
          // Fetch full status for the selected run to get theme/story info
          try {
            const status = await api.pipeline.status(latestRun.id);
            setSelectedRunStatus(status);
          } catch (err) {
            console.error("Failed to fetch run status:", err);
            setSelectedRunStatus(null);
          }
          // Guard against null started_at (R1 fix)
          if (latestRun.started_at) {
            await fetchStoriesCreatedSince(latestRun.started_at);
          }
        }
      }

      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load pipeline data",
      );
    } finally {
      setLoading(false);
    }
  }, [fetchStoriesCreatedSince]); // Removed selectedRunId from deps (R2/D1 fix)

  // Poll for status updates when run is active
  const pollStatus = useCallback(async () => {
    if (!activeStatus) return;

    try {
      const status = await api.pipeline.status(activeStatus.id);
      setActiveStatus(status);

      // Stop polling if run completed
      if (["completed", "failed", "stopped"].includes(status.status)) {
        setActiveStatus(null);
        fetchData(); // Refresh history
      }
    } catch (err) {
      console.error("Status poll error:", err);
    }
  }, [activeStatus, fetchData]);

  // Setup polling
  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (activeStatus && ["running", "stopping"].includes(activeStatus.status)) {
      pollingRef.current = setInterval(pollStatus, STATUS_POLL_INTERVAL);
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [activeStatus, pollStatus]);

  const handleStart = async () => {
    setIsStarting(true);
    setError(null);

    try {
      const request: PipelineRunRequest = {
        days: formState.days,
        dry_run: formState.dryRun,
        concurrency: formState.concurrency,
        auto_create_stories: formState.autoCreateStories,
      };

      if (formState.maxConversations) {
        request.max_conversations = parseInt(formState.maxConversations, 10);
      }

      const response = await api.pipeline.run(request);
      const status = await api.pipeline.status(response.run_id);
      setActiveStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    } finally {
      setIsStarting(false);
    }
  };

  const handleCreateStories = async (runId: number) => {
    setIsCreatingStories(true);
    setError(null);

    try {
      await api.pipeline.createStories(runId);
      // Refresh data to get updated status and new stories
      await fetchData();
      // Fetch stories for the selected run
      if (selectedRunId) {
        const selectedRun = history.find((r) => r.id === selectedRunId);
        if (selectedRun?.started_at) {
          await fetchStoriesCreatedSince(selectedRun.started_at);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create stories");
    } finally {
      setIsCreatingStories(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    setError(null);

    try {
      await api.pipeline.stop();
      // Refresh status
      if (activeStatus) {
        const status = await api.pipeline.status(activeStatus.id);
        setActiveStatus(status);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop pipeline");
    } finally {
      setIsStopping(false);
    }
  };

  const isRunning = Boolean(
    activeStatus && ["running", "stopping"].includes(activeStatus.status),
  );

  // Handle clicking on a run in history to view its new stories
  const handleRunClick = useCallback(
    async (run: PipelineRunListItem) => {
      if (run.status !== "completed" || !run.started_at) return;
      // Mark that user has manually selected a run (prevents auto-selection override)
      hasUserSelectedRunRef.current = true;
      setSelectedRunId(run.id);
      // Fetch full status for the selected run to get theme/story info
      try {
        const status = await api.pipeline.status(run.id);
        setSelectedRunStatus(status);
      } catch (err) {
        console.error("Failed to fetch run status:", err);
        setSelectedRunStatus(null);
      }
      await fetchStoriesCreatedSince(run.started_at);
    },
    [fetchStoriesCreatedSince],
  );

  if (loading) {
    return (
      <div className="loading-container loading-delayed">
        <div className="loading-spinner" />
        <span>Loading pipeline...</span>
        <style jsx>{`
          .loading-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            gap: 16px;
            color: var(--text-secondary);
            font-size: 14px;
          }
          .loading-spinner {
            width: 28px;
            height: 28px;
            border: 3px solid var(--border-default);
            border-top-color: var(--accent-blue);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
          }
          @keyframes spin {
            to {
              transform: rotate(360deg);
            }
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="pipeline-layout">
      <header className="pipeline-header">
        <div className="header-left">
          <Link href="/" className="logo-link">
            <FeedForwardLogo size="sm" />
          </Link>
          <div className="header-divider" />
          <span className="page-subtitle">Pipeline Control</span>
        </div>

        <div className="header-actions">
          <Link href="/" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            Board
          </Link>
          <Link href="/analytics" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M18 20V10" />
              <path d="M12 20V4" />
              <path d="M6 20v-6" />
            </svg>
            Analytics
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="pipeline-content">
        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button onClick={() => setError(null)}>Dismiss</button>
          </div>
        )}

        <div className="content-grid">
          {/* Run Configuration */}
          <section className="config-section">
            <h2>Run Configuration</h2>
            <div className="config-form">
              <div className="form-group">
                <label htmlFor="days">Days to Process</label>
                <input
                  id="days"
                  type="number"
                  min="1"
                  max="90"
                  value={formState.days}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      days: parseInt(e.target.value, 10) || 7,
                    })
                  }
                  disabled={isRunning}
                />
                <span className="form-hint">
                  Look back this many days for conversations
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="maxConversations">
                  Max Conversations (optional)
                </label>
                <input
                  id="maxConversations"
                  type="number"
                  min="1"
                  placeholder="No limit"
                  value={formState.maxConversations}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      maxConversations: e.target.value,
                    })
                  }
                  disabled={isRunning}
                />
                <span className="form-hint">
                  Limit for testing (leave empty for all)
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="concurrency">Concurrency</label>
                <input
                  id="concurrency"
                  type="number"
                  min="1"
                  max="50"
                  value={formState.concurrency}
                  onChange={(e) =>
                    setFormState({
                      ...formState,
                      concurrency: parseInt(e.target.value, 10) || 20,
                    })
                  }
                  disabled={isRunning}
                />
                <span className="form-hint">
                  Parallel API calls (higher = faster)
                </span>
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formState.dryRun}
                    onChange={(e) =>
                      setFormState({ ...formState, dryRun: e.target.checked })
                    }
                    disabled={isRunning}
                  />
                  <span>Dry Run</span>
                </label>
                <span className="form-hint">
                  Classify but don&apos;t store to database
                </span>
              </div>

              <div className="form-group checkbox-group">
                <label>
                  <input
                    type="checkbox"
                    checked={formState.autoCreateStories}
                    onChange={(e) =>
                      setFormState({
                        ...formState,
                        autoCreateStories: e.target.checked,
                      })
                    }
                    disabled={isRunning || formState.dryRun}
                  />
                  <span>Auto-create stories after run</span>
                </label>
                <span className="form-hint">
                  Automatically run PM review and create stories when pipeline
                  completes
                </span>
              </div>

              <div className="action-buttons">
                {!isRunning ? (
                  <button
                    className="btn-primary"
                    onClick={handleStart}
                    disabled={isStarting}
                  >
                    {isStarting ? "Starting..." : "Start Pipeline Run"}
                  </button>
                ) : (
                  <button
                    className="btn-danger"
                    onClick={handleStop}
                    disabled={isStopping || activeStatus?.status === "stopping"}
                  >
                    {activeStatus?.status === "stopping"
                      ? "Stopping..."
                      : isStopping
                        ? "Sending stop signal..."
                        : "Stop Pipeline"}
                  </button>
                )}
              </div>
            </div>
          </section>

          {/* Active Run Status */}
          <section className="status-section">
            <h2>Active Run Status</h2>
            {activeStatus ? (
              <div className="status-panel">
                <div className="status-header">
                  <span className="run-id">Run #{activeStatus.id}</span>
                  <span
                    className="status-badge"
                    style={{
                      backgroundColor: getStatusColor(activeStatus.status),
                    }}
                  >
                    {activeStatus.status}
                  </span>
                </div>

                {/* Phase indicator when running */}
                {activeStatus.status === "running" &&
                  activeStatus.current_phase && (
                    <div className="phase-indicator">
                      <div className="phase-spinner" />
                      <span className="phase-label">
                        {getPhaseLabel(activeStatus.current_phase)}
                      </span>
                    </div>
                  )}

                <div className="status-grid">
                  <div className="stat-item">
                    <span className="stat-value">
                      {activeStatus.conversations_fetched}
                    </span>
                    <span className="stat-label">Fetched</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-value">
                      {activeStatus.conversations_filtered}
                    </span>
                    <span className="stat-label">Filtered</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-value">
                      {activeStatus.conversations_classified}
                    </span>
                    <span className="stat-label">Classified</span>
                  </div>
                  <div className="stat-item">
                    <span className="stat-value">
                      {activeStatus.conversations_stored}
                    </span>
                    <span className="stat-label">Stored</span>
                  </div>
                </div>

                {/* Theme/Story extraction stats when available */}
                {(activeStatus.themes_extracted > 0 ||
                  activeStatus.stories_created > 0) && (
                  <div className="status-grid secondary">
                    <div className="stat-item">
                      <span className="stat-value">
                        {activeStatus.themes_extracted}
                      </span>
                      <span className="stat-label">Themes</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">
                        {activeStatus.themes_new}
                      </span>
                      <span className="stat-label">New Signatures</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">
                        {activeStatus.stories_created}
                      </span>
                      <span className="stat-label">Stories</span>
                    </div>
                    <div className="stat-item">
                      <span className="stat-value">
                        {activeStatus.orphans_created}
                      </span>
                      <span className="stat-label">Orphans</span>
                    </div>
                  </div>
                )}

                <div className="status-meta">
                  <div className="meta-item">
                    <span className="meta-label">Started:</span>
                    <span className="meta-value">
                      {formatDate(activeStatus.started_at)}
                    </span>
                  </div>
                  <div className="meta-item">
                    <span className="meta-label">Duration:</span>
                    <span className="meta-value">
                      {formatDuration(activeStatus.duration_seconds)}
                    </span>
                  </div>
                </div>

                {activeStatus.error_message && (
                  <div className="error-message">
                    <strong>Error:</strong> {activeStatus.error_message}
                  </div>
                )}
              </div>
            ) : (
              <div className="no-active-run">
                <svg
                  width="48"
                  height="48"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <circle cx="12" cy="12" r="10" />
                  <path d="M12 6v6l4 2" />
                </svg>
                <span>No active pipeline run</span>
                <span className="hint">
                  Start a new run using the configuration form
                </span>
              </div>
            )}
          </section>

          {/* Run History */}
          <section className="history-section">
            <h2>Run History</h2>
            <p className="history-hint">
              Click a completed run to see stories created during that run
            </p>
            {history.length > 0 ? (
              <div className="history-table">
                <div className="table-header">
                  <span>ID</span>
                  <span>Status</span>
                  <span>Started</span>
                  <span>Duration</span>
                  <span>Fetched</span>
                  <span>Classified</span>
                  <span>Stored</span>
                </div>
                {history.map((run) => (
                  <div
                    key={run.id}
                    className={`table-row ${run.status === "completed" ? "clickable" : ""} ${selectedRunId === run.id ? "selected" : ""}`}
                    onClick={() => handleRunClick(run)}
                    role={run.status === "completed" ? "button" : undefined}
                    tabIndex={run.status === "completed" ? 0 : undefined}
                    onKeyDown={(e) => {
                      if (
                        run.status === "completed" &&
                        (e.key === "Enter" || e.key === " ")
                      ) {
                        handleRunClick(run);
                      }
                    }}
                  >
                    <span className="run-id">#{run.id}</span>
                    <span>
                      <span
                        className="status-dot"
                        style={{ backgroundColor: getStatusColor(run.status) }}
                      />
                      {run.status}
                    </span>
                    <span>{formatDate(run.started_at)}</span>
                    <span>{formatDuration(run.duration_seconds)}</span>
                    <span>{run.conversations_fetched}</span>
                    <span>{run.conversations_classified}</span>
                    <span>{run.conversations_stored}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="no-history">
                <span>No pipeline runs yet</span>
              </div>
            )}
          </section>

          {/* Adaptive Run Results Panel */}
          {selectedRunId && selectedRunStatus && (
            <section className="run-results-section">
              {/* Stories Created Mode */}
              {selectedRunStatus.stories_created > 0 ? (
                <>
                  <h2>
                    Stories Created
                    <span className="story-count">({newStories.length})</span>
                  </h2>
                  {newStories.length > 0 ? (
                    <div className="stories-list">
                      {newStories.map((story) => (
                        <Link
                          key={story.id}
                          href={`/story/${story.id}`}
                          className="story-card"
                        >
                          <div className="story-header">
                            <span className="story-title">{story.title}</span>
                            <span
                              className="story-status"
                              style={{
                                backgroundColor:
                                  story.status === "candidate"
                                    ? "var(--accent-amber)"
                                    : story.status === "triaged"
                                      ? "var(--accent-blue)"
                                      : "var(--text-tertiary)",
                              }}
                            >
                              {story.status}
                            </span>
                          </div>
                          {story.description && (
                            <p className="story-description">
                              {story.description.length > 120
                                ? `${story.description.substring(0, 120)}...`
                                : story.description}
                            </p>
                          )}
                          <div className="story-meta">
                            {story.product_area && (
                              <span className="story-area">
                                {story.product_area}
                              </span>
                            )}
                            <span className="story-date">
                              {formatDate(story.created_at)}
                            </span>
                          </div>
                        </Link>
                      ))}
                    </div>
                  ) : (
                    <div className="no-stories">
                      <svg
                        width="32"
                        height="32"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                      >
                        <path d="M9 12h6M12 9v6" />
                        <rect x="3" y="5" width="18" height="14" rx="2" />
                      </svg>
                      <span>No new stories from this run</span>
                    </div>
                  )}
                </>
              ) : selectedRunStatus.stories_ready &&
                selectedRunStatus.themes_extracted > 0 ? (
                /* Themes Extracted Mode - Ready for Story Creation */
                <>
                  <h2>Themes Extracted</h2>
                  <div className="themes-ready-panel">
                    <div className="themes-stats">
                      <div className="stat-highlight">
                        <span className="stat-value">
                          {selectedRunStatus.themes_extracted}
                        </span>
                        <span className="stat-label">themes extracted</span>
                      </div>
                      <div className="stat-detail">
                        <span className="stat-value">
                          {selectedRunStatus.themes_new}
                        </span>
                        <span className="stat-label">new signatures</span>
                      </div>
                    </div>
                    <p className="ready-message">
                      Review themes and create stories when ready
                    </p>
                    <button
                      className="btn-create-stories"
                      onClick={() => handleCreateStories(selectedRunId)}
                      disabled={isCreatingStories}
                    >
                      {isCreatingStories ? (
                        <>
                          <span className="btn-spinner" />
                          Creating Stories...
                        </>
                      ) : (
                        "Create Stories"
                      )}
                    </button>
                  </div>
                </>
              ) : selectedRunStatus.themes_extracted > 0 ? (
                /* Themes Extracted but not ready for stories (e.g., dry run) */
                <>
                  <h2>Themes Extracted</h2>
                  <div className="themes-extracted-panel">
                    <div className="themes-stats">
                      <div className="stat-highlight">
                        <span className="stat-value">
                          {selectedRunStatus.themes_extracted}
                        </span>
                        <span className="stat-label">themes extracted</span>
                      </div>
                      <div className="stat-detail">
                        <span className="stat-value">
                          {selectedRunStatus.themes_new}
                        </span>
                        <span className="stat-label">new signatures</span>
                      </div>
                    </div>
                    <p className="info-message">
                      Run completed. Themes were extracted during this pipeline
                      run.
                    </p>
                  </div>
                </>
              ) : (
                /* No themes or stories - default empty state */
                <div className="no-stories">
                  <svg
                    width="32"
                    height="32"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  >
                    <path d="M9 12h6M12 9v6" />
                    <rect x="3" y="5" width="18" height="14" rx="2" />
                  </svg>
                  <span>No themes or stories from this run</span>
                </div>
              )}
            </section>
          )}
        </div>
      </main>

      <style jsx>{`
        .pipeline-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }

        .pipeline-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 24px;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 22%),
            hsl(0, 0%, 18%)
          );
          box-shadow: var(--shadow-md);
          position: sticky;
          top: 16px;
          margin: 16px 24px 0;
          border-radius: var(--radius-full);
          z-index: 10;
          gap: 20px;
        }

        :global([data-theme="light"]) .pipeline-header {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 94%)
          );
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 14px;
          flex-shrink: 0;
        }

        .logo-link {
          display: flex;
          align-items: center;
        }

        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }

        .page-subtitle {
          font-size: 16px;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-shrink: 0;
        }

        .header-actions :global(.nav-link) {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          border-radius: var(--radius-full);
          font-size: 13px;
          font-weight: 500;
          color: var(--text-secondary);
          text-decoration: none;
          transition: all 0.15s ease;
        }

        .header-actions :global(.nav-link):hover {
          color: var(--text-primary);
          background: var(--bg-hover);
        }

        .pipeline-content {
          flex: 1;
          padding: 24px 28px;
          max-width: 1200px;
          margin: 0 auto;
          width: 100%;
        }

        .error-banner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 16px;
          background: var(--accent-red);
          color: white;
          border-radius: var(--radius-md);
          margin-bottom: 24px;
        }

        .error-banner button {
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: white;
          padding: 4px 12px;
          border-radius: var(--radius-sm);
          cursor: pointer;
        }

        .content-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 24px;
        }

        .config-section,
        .status-section,
        .history-section {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border-radius: var(--radius-lg);
          padding: 20px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .config-section,
        :global([data-theme="light"]) .status-section,
        :global([data-theme="light"]) .history-section {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .history-section {
          grid-column: 1 / -1;
        }

        h2 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 16px 0;
        }

        .config-form {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }

        .form-group label {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .form-group input[type="number"],
        .form-group input[type="text"] {
          padding: 10px 12px;
          background: var(--bg-elevated);
          border: none;
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-size: 14px;
          box-shadow: var(--shadow-inset);
        }

        .form-group input:focus {
          outline: 2px solid var(--accent-blue);
          outline-offset: -2px;
        }

        .form-group input:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .form-hint {
          font-size: 11px;
          color: var(--text-tertiary);
        }

        .checkbox-group label {
          display: flex;
          align-items: center;
          gap: 8px;
          cursor: pointer;
        }

        .checkbox-group input[type="checkbox"] {
          width: 16px;
          height: 16px;
          accent-color: var(--accent-blue);
        }

        .action-buttons {
          margin-top: 8px;
        }

        .btn-primary,
        .btn-danger {
          width: 100%;
          padding: 12px 20px;
          border: none;
          border-radius: var(--radius-md);
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .btn-primary {
          background: var(--accent-blue);
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: #74b3ff;
        }

        .btn-primary:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-danger {
          background: var(--accent-red);
          color: white;
        }

        .btn-danger:hover:not(:disabled) {
          background: #ff6b6b;
        }

        .btn-danger:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .status-panel {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .status-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .run-id {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .status-badge {
          padding: 4px 10px;
          border-radius: var(--radius-full);
          font-size: 11px;
          font-weight: 600;
          color: white;
          text-transform: uppercase;
        }

        .status-grid {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 12px;
        }

        .stat-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          padding: 12px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
        }

        :global([data-theme="light"]) .stat-item {
          background: var(--bg-hover);
        }

        .stat-value {
          font-size: 24px;
          font-weight: 600;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .stat-label {
          font-size: 11px;
          font-weight: 500;
          color: var(--text-tertiary);
          text-transform: uppercase;
        }

        .status-meta {
          display: flex;
          gap: 24px;
        }

        .meta-item {
          display: flex;
          gap: 8px;
          font-size: 13px;
        }

        .meta-label {
          color: var(--text-tertiary);
        }

        .meta-value {
          color: var(--text-secondary);
        }

        .error-message {
          padding: 12px;
          background: rgba(255, 82, 82, 0.1);
          border-radius: var(--radius-md);
          color: var(--accent-red);
          font-size: 13px;
        }

        .no-active-run {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 32px;
          gap: 12px;
          color: var(--text-tertiary);
        }

        .no-active-run svg {
          opacity: 0.5;
        }

        .no-active-run span {
          font-size: 14px;
        }

        .no-active-run .hint {
          font-size: 12px;
          opacity: 0.7;
        }

        .history-table {
          display: flex;
          flex-direction: column;
        }

        .table-header,
        .table-row {
          display: grid;
          grid-template-columns: 60px 100px 1fr 80px 80px 80px 80px;
          gap: 12px;
          padding: 12px;
          align-items: center;
        }

        .table-header {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-tertiary);
          text-transform: uppercase;
          border-bottom: 1px solid var(--border-subtle);
        }

        .table-row {
          font-size: 13px;
          color: var(--text-secondary);
          border-bottom: 1px solid var(--border-subtle);
        }

        .table-row:last-child {
          border-bottom: none;
        }

        .table-row:hover {
          background: var(--bg-hover);
        }

        .table-row .run-id {
          font-size: 13px;
          color: var(--text-primary);
        }

        .status-dot {
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          margin-right: 6px;
        }

        .no-history {
          display: flex;
          justify-content: center;
          padding: 32px;
          color: var(--text-tertiary);
          font-size: 14px;
        }

        .history-hint {
          font-size: 12px;
          color: var(--text-tertiary);
          margin: 0 0 12px 0;
        }

        .table-row.clickable {
          cursor: pointer;
        }

        .table-row.selected {
          background: var(--bg-hover);
          border-left: 3px solid var(--accent-blue);
        }

        /* Phase Indicator */
        .phase-indicator {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 10px 14px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
          border-left: 3px solid var(--accent-blue);
        }

        .phase-spinner {
          width: 16px;
          height: 16px;
          border: 2px solid var(--border-default);
          border-top-color: var(--accent-blue);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        .phase-label {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
        }

        .status-grid.secondary {
          margin-top: 12px;
          padding-top: 12px;
          border-top: 1px solid var(--border-subtle);
        }

        /* Run Results Section */
        .run-results-section {
          grid-column: 1 / -1;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border-radius: var(--radius-lg);
          padding: 20px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .run-results-section {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .run-results-section h2 {
          display: flex;
          align-items: center;
          gap: 8px;
        }

        /* Themes Ready Panel */
        .themes-ready-panel,
        .themes-extracted-panel {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
          padding: 24px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
        }

        :global([data-theme="light"]) .themes-ready-panel,
        :global([data-theme="light"]) .themes-extracted-panel {
          background: var(--bg-hover);
        }

        .themes-stats {
          display: flex;
          gap: 32px;
        }

        .stat-highlight,
        .stat-detail {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
        }

        .stat-highlight .stat-value {
          font-size: 32px;
          font-weight: 600;
          color: var(--accent-blue);
        }

        .stat-detail .stat-value {
          font-size: 24px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .themes-stats .stat-label {
          font-size: 12px;
          color: var(--text-tertiary);
        }

        .ready-message,
        .info-message {
          font-size: 14px;
          color: var(--text-secondary);
          text-align: center;
          margin: 0;
        }

        .btn-create-stories {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
          padding: 12px 24px;
          background: var(--accent-blue);
          color: white;
          border: none;
          border-radius: var(--radius-md);
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.2s ease;
          min-width: 180px;
        }

        .btn-create-stories:hover:not(:disabled) {
          background: #74b3ff;
          transform: translateY(-1px);
        }

        .btn-create-stories:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .btn-spinner {
          width: 14px;
          height: 14px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        .story-count {
          font-weight: 400;
          color: var(--text-tertiary);
          font-size: 13px;
        }

        .stories-list {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
          gap: 12px;
        }

        .story-card {
          display: flex;
          flex-direction: column;
          gap: 8px;
          padding: 14px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
          text-decoration: none;
          transition: all 0.15s ease;
        }

        :global([data-theme="light"]) .story-card {
          background: var(--bg-hover);
        }

        .story-card:hover {
          background: var(--bg-hover);
          transform: translateY(-1px);
        }

        :global([data-theme="light"]) .story-card:hover {
          background: var(--border-default);
        }

        .story-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 8px;
        }

        .story-title {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-primary);
          line-height: 1.3;
        }

        .story-status {
          padding: 2px 8px;
          border-radius: var(--radius-full);
          font-size: 10px;
          font-weight: 600;
          color: white;
          text-transform: uppercase;
          flex-shrink: 0;
        }

        .story-description {
          font-size: 12px;
          color: var(--text-secondary);
          line-height: 1.4;
          margin: 0;
        }

        .story-meta {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: auto;
        }

        .story-area {
          font-size: 11px;
          color: var(--text-tertiary);
          background: var(--bg-subtle);
          padding: 2px 6px;
          border-radius: var(--radius-sm);
        }

        .story-date {
          font-size: 11px;
          color: var(--text-tertiary);
          margin-left: auto;
        }

        .no-stories {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 32px;
          gap: 12px;
          color: var(--text-tertiary);
        }

        .no-stories svg {
          opacity: 0.5;
        }

        .no-stories span {
          font-size: 14px;
        }

        @media (max-width: 768px) {
          .content-grid {
            grid-template-columns: 1fr;
          }

          .status-grid {
            grid-template-columns: repeat(2, 1fr);
          }

          .table-header,
          .table-row {
            grid-template-columns: 50px 80px 1fr 60px 60px;
          }

          .table-header span:nth-child(6),
          .table-header span:nth-child(7),
          .table-row span:nth-child(6),
          .table-row span:nth-child(7) {
            display: none;
          }
        }
      `}</style>
    </div>
  );
}
