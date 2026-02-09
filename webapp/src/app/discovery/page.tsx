"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DiscoveryRun } from "@/lib/types";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";

export default function DiscoveryPage() {
  const [runs, setRuns] = useState<DiscoveryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.discovery
      .listRuns()
      .then(setRuns)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <span>Loading discovery runs...</span>
      </div>
    );
  }

  return (
    <div className="discovery-layout">
      <header className="discovery-header">
        <div className="header-left">
          <Link href="/">
            <FeedForwardLogo size="sm" />
          </Link>
          <div className="header-divider" />
          <span className="page-title">Discovery</span>
          <span className="run-count">{runs.length} runs</span>
        </div>
      </header>

      <main className="discovery-content">
        {error && <p className="error-msg">{error}</p>}

        {runs.length === 0 && !error && (
          <p className="empty-msg">No discovery runs yet.</p>
        )}

        <div className="run-list">
          {runs.map((run) => (
            <Link
              key={run.id}
              href={`/discovery/${run.id}`}
              className="run-card"
            >
              <div className="run-top">
                <span className={`run-status status-${run.status}`}>
                  {run.status}
                </span>
                {run.current_stage && (
                  <span className="run-stage">
                    {run.current_stage.replace(/_/g, " ")}
                  </span>
                )}
                {run.parent_run_id && (
                  <span className="run-reentry">Re-entry</span>
                )}
              </div>
              <div className="run-id">{run.id.slice(0, 8)}...</div>
              <div className="run-meta">
                <span>{run.opportunity_count} opportunities</span>
                <span>{run.stages_completed} stages done</span>
                {run.started_at && (
                  <span>{new Date(run.started_at).toLocaleDateString()}</span>
                )}
              </div>
            </Link>
          ))}
        </div>
      </main>

      <style jsx>{`
        .discovery-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }
        .discovery-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 24px;
          background: var(--bg-surface);
          box-shadow: var(--shadow-sm);
        }
        .header-left {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }
        .page-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .run-count {
          font-size: 13px;
          color: var(--text-secondary);
          background: var(--bg-elevated);
          padding: 4px 10px;
          border-radius: 12px;
        }
        .discovery-content {
          flex: 1;
          padding: 24px;
          max-width: 900px;
          margin: 0 auto;
          width: 100%;
        }
        .error-msg {
          color: var(--accent-red);
          font-size: 14px;
        }
        .empty-msg {
          color: var(--text-secondary);
          font-size: 14px;
          text-align: center;
          margin-top: 40px;
        }
        .run-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .run-card {
          display: block;
          padding: 16px;
          background: var(--bg-surface);
          border-radius: var(--radius-md);
          text-decoration: none;
          color: var(--text-primary);
          transition: all 0.15s ease;
          box-shadow: var(--shadow-sm);
        }
        .run-card:hover {
          box-shadow: var(--shadow-md);
          background: var(--bg-elevated);
        }
        .run-top {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 6px;
        }
        .run-status {
          font-size: 12px;
          font-weight: 600;
          text-transform: capitalize;
          padding: 2px 8px;
          border-radius: 4px;
        }
        .status-running {
          color: var(--accent-blue);
          background: hsla(217, 91%, 60%, 0.15);
        }
        .status-completed {
          color: var(--accent-green);
          background: hsla(160, 64%, 52%, 0.15);
        }
        .status-failed {
          color: var(--accent-red);
          background: hsla(0, 72%, 51%, 0.15);
        }
        .status-pending {
          color: var(--accent-amber);
          background: hsla(38, 92%, 50%, 0.15);
        }
        .status-stopped {
          color: var(--text-muted);
          background: var(--bg-elevated);
        }
        .run-stage {
          font-size: 12px;
          color: var(--text-tertiary);
          text-transform: capitalize;
        }
        .run-reentry {
          font-size: 11px;
          color: var(--accent-purple, #a78bfa);
          border: 1px solid currentColor;
          padding: 1px 6px;
          border-radius: 4px;
        }
        .run-id {
          font-size: 13px;
          font-family: var(--font-geist-mono);
          color: var(--text-secondary);
          margin-bottom: 6px;
        }
        .run-meta {
          display: flex;
          gap: 16px;
          font-size: 12px;
          color: var(--text-tertiary);
        }
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
