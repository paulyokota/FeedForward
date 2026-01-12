"use client";

import { useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import type { SyncStatusResponse, SyncResult, SyncState } from "@/lib/types";
import { getSyncState, SYNC_STATE_CONFIG } from "@/lib/types";
import { SyncStatusBadge } from "./SyncStatusBadge";

interface ShortcutSyncPanelProps {
  storyId: string;
  initialSyncStatus?: SyncStatusResponse | null;
  onSyncComplete?: (result: SyncResult) => void;
}

function formatTimeAgo(dateString: string | null): string {
  if (!dateString) return "Never";
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function ShortcutSyncPanel({
  storyId,
  initialSyncStatus,
  onSyncComplete,
}: ShortcutSyncPanelProps) {
  const [syncStatus, setSyncStatus] = useState<SyncStatusResponse | null>(
    initialSyncStatus ?? null,
  );
  const [isLoading, setIsLoading] = useState(!initialSyncStatus);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isPulling, setIsPulling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const status = await api.sync.getStatus(storyId);
      setSyncStatus(status);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to fetch sync status",
      );
    } finally {
      setIsLoading(false);
    }
  }, [storyId]);

  useEffect(() => {
    if (!initialSyncStatus) {
      fetchStatus();
    }
  }, [fetchStatus, initialSyncStatus]);

  const handleSync = async () => {
    try {
      setIsSyncing(true);
      setError(null);
      const result = await api.sync.syncStory(storyId);
      if (result.success) {
        await fetchStatus();
        onSyncComplete?.(result);
      } else {
        setError(result.error || "Sync failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setIsSyncing(false);
    }
  };

  const handlePush = async () => {
    try {
      setIsSyncing(true);
      setError(null);
      const response = await api.sync.push(storyId);
      await fetchStatus();
      onSyncComplete?.({
        success: true,
        direction: "push",
        story_id: storyId,
        shortcut_story_id: response.shortcut_story_id,
        error: null,
        synced_at: response.last_synced_at,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Push failed");
    } finally {
      setIsSyncing(false);
    }
  };

  const handlePull = async () => {
    if (!syncStatus?.shortcut_story_id) return;
    try {
      setIsPulling(true);
      setError(null);
      await api.sync.pull(syncStatus.shortcut_story_id, storyId);
      await fetchStatus();
      onSyncComplete?.({
        success: true,
        direction: "pull",
        story_id: storyId,
        shortcut_story_id: syncStatus.shortcut_story_id,
        error: null,
        synced_at: new Date().toISOString(),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pull failed");
    } finally {
      setIsPulling(false);
    }
  };

  const handleRetry = () => {
    setError(null);
    fetchStatus();
  };

  const syncState: SyncState = getSyncState(syncStatus?.last_sync_status);
  const isLinked = !!syncStatus?.shortcut_story_id;
  const shortcutUrl = syncStatus?.shortcut_story_id
    ? `https://app.shortcut.com/story/${syncStatus.shortcut_story_id}`
    : null;

  if (isLoading) {
    return (
      <div className="sync-panel">
        <div className="sync-panel-loading">
          <div className="spinner" />
          <span>Loading sync status...</span>
        </div>
        <style jsx>{`
          .sync-panel {
            background: linear-gradient(
              to bottom,
              hsl(0, 0%, 16%),
              hsl(0, 0%, 12%)
            );
            border: 1px solid var(--border-default);
            border-radius: var(--radius-lg);
            padding: 16px;
          }

          :global([data-theme="light"]) .sync-panel {
            background: linear-gradient(
              to bottom,
              hsl(0, 0%, 100%),
              hsl(0, 0%, 97%)
            );
          }

          .sync-panel-loading {
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--text-secondary);
            font-size: 13px;
          }

          .spinner {
            width: 16px;
            height: 16px;
            border: 2px solid var(--border-default);
            border-top-color: var(--accent-teal);
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
    <div className="sync-panel">
      <div className="sync-header">
        <div className="sync-title">
          <ShortcutIcon />
          <span>Shortcut Sync</span>
        </div>
        <SyncStatusBadge state={syncState} size="md" showLabel />
      </div>

      <div className="sync-info">
        <div className="sync-row">
          <span className="sync-label">Last synced:</span>
          <span className="sync-value">
            {formatTimeAgo(syncStatus?.last_synced_at ?? null)}
          </span>
        </div>
        {isLinked && shortcutUrl && (
          <div className="sync-row">
            <span className="sync-label">Shortcut ID:</span>
            <a
              href={shortcutUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="shortcut-link"
            >
              {syncStatus?.shortcut_story_id}
              <ExternalLinkIcon />
            </a>
          </div>
        )}
        {syncStatus?.last_sync_direction && (
          <div className="sync-row">
            <span className="sync-label">Last direction:</span>
            <span className="sync-value capitalize">
              {syncStatus.last_sync_direction}
            </span>
          </div>
        )}
      </div>

      {error && (
        <div className="sync-error">
          <div className="error-message">{error}</div>
          <button className="retry-btn" onClick={handleRetry}>
            Retry
          </button>
        </div>
      )}

      <div className="sync-actions">
        {!isLinked ? (
          <button
            className="btn-primary"
            onClick={handlePush}
            disabled={isSyncing}
          >
            {isSyncing ? (
              <>
                <span className="btn-spinner" />
                Linking...
              </>
            ) : (
              "Link to Shortcut"
            )}
          </button>
        ) : (
          <>
            <button
              className="btn-primary"
              onClick={handleSync}
              disabled={isSyncing || isPulling}
            >
              {isSyncing ? (
                <>
                  <span className="btn-spinner" />
                  Syncing...
                </>
              ) : (
                "Sync Now"
              )}
            </button>
            <button
              className="btn-secondary"
              onClick={handlePull}
              disabled={isSyncing || isPulling}
            >
              {isPulling ? (
                <>
                  <span className="btn-spinner" />
                  Refreshing...
                </>
              ) : (
                "Refresh from Shortcut"
              )}
            </button>
          </>
        )}
      </div>

      <style jsx>{`
        .sync-panel {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border: 1px solid var(--border-default);
          border-radius: var(--radius-lg);
          padding: 16px;
          box-shadow: var(--shadow-md);
        }

        :global([data-theme="light"]) .sync-panel {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .sync-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 14px;
          padding-bottom: 12px;
          border-bottom: 1px solid var(--border-subtle);
        }

        .sync-title {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .sync-info {
          margin-bottom: 14px;
        }

        .sync-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 6px 0;
          font-size: 13px;
        }

        .sync-label {
          color: var(--text-secondary);
        }

        .sync-value {
          color: var(--text-primary);
        }

        .sync-value.capitalize {
          text-transform: capitalize;
        }

        .shortcut-link {
          display: inline-flex;
          align-items: center;
          gap: 5px;
          color: var(--accent-teal);
          text-decoration: none;
          font-family: monospace;
          font-size: 12px;
          transition: opacity 0.15s ease;
        }

        .shortcut-link:hover {
          opacity: 0.8;
          text-decoration: underline;
        }

        .sync-error {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 10px;
          background: var(--accent-red-dim, rgba(239, 68, 68, 0.1));
          border: 1px solid var(--accent-red);
          border-radius: var(--radius-md);
          padding: 10px 12px;
          margin-bottom: 14px;
        }

        .error-message {
          color: var(--accent-red);
          font-size: 13px;
          flex: 1;
        }

        .retry-btn {
          background: transparent;
          border: 1px solid var(--accent-red);
          color: var(--accent-red);
          padding: 4px 10px;
          border-radius: var(--radius-md);
          font-size: 12px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .retry-btn:hover {
          background: var(--accent-red);
          color: white;
        }

        .sync-actions {
          display: flex;
          gap: 10px;
        }

        .btn-primary,
        .btn-secondary {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 6px;
          padding: 9px 14px;
          border-radius: var(--radius-md);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
          flex: 1;
        }

        .btn-primary {
          background: linear-gradient(
            to bottom,
            hsl(187, 84%, 58%),
            hsl(187, 84%, 48%)
          );
          border: none;
          color: hsl(0, 0%, 5%);
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .btn-primary {
          background: linear-gradient(
            to bottom,
            hsl(187, 90%, 38%),
            hsl(187, 90%, 28%)
          );
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: linear-gradient(
            to bottom,
            hsl(187, 84%, 63%),
            hsl(187, 84%, 53%)
          );
        }

        :global([data-theme="light"]) .btn-primary:hover:not(:disabled) {
          background: linear-gradient(
            to bottom,
            hsl(187, 90%, 42%),
            hsl(187, 90%, 32%)
          );
        }

        .btn-primary:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-secondary {
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          color: var(--text-secondary);
        }

        .btn-secondary:hover:not(:disabled) {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        .btn-secondary:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .btn-spinner {
          width: 12px;
          height: 12px;
          border: 2px solid rgba(255, 255, 255, 0.3);
          border-top-color: white;
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

function ShortcutIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71" />
      <path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}
