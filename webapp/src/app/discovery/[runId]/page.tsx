"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DiscoveryRunDetail, RankedOpportunity } from "@/lib/types";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import { OpportunityCard } from "@/components/discovery/OpportunityCard";

export default function RunDetailPage() {
  const params = useParams();
  const runId = params.runId as string;

  const [run, setRun] = useState<DiscoveryRunDetail | null>(null);
  const [opportunities, setOpportunities] = useState<RankedOpportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.discovery.getRun(runId),
      api.discovery.getOpportunities(runId),
    ])
      .then(([runData, oppData]) => {
        setRun(runData);
        setOpportunities(oppData);
      })
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
  }, [runId]);

  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <span>Loading run...</span>
      </div>
    );
  }

  if (error || !run) {
    return (
      <div className="error-container">
        <p>{error || "Run not found"}</p>
        <Link href="/discovery">Back to runs</Link>
      </div>
    );
  }

  const reviewedCount = opportunities.filter((o) => o.review_status).length;

  return (
    <div className="run-layout">
      <header className="run-header">
        <div className="header-left">
          <Link href="/">
            <FeedForwardLogo size="sm" />
          </Link>
          <div className="header-divider" />
          <Link href="/discovery" className="breadcrumb">
            Discovery
          </Link>
          <span className="breadcrumb-sep">/</span>
          <span className="page-title">{run.id.slice(0, 8)}...</span>
          <span className={`run-status status-${run.status}`}>
            {run.status}
          </span>
        </div>
      </header>

      <main className="run-content">
        <div className="run-summary">
          <div className="summary-item">
            <span className="summary-label">Stage</span>
            <span className="summary-value">
              {run.current_stage?.replace(/_/g, " ") || "N/A"}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Opportunities</span>
            <span className="summary-value">{opportunities.length}</span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Reviewed</span>
            <span className="summary-value">
              {reviewedCount} / {opportunities.length}
            </span>
          </div>
          <div className="summary-item">
            <span className="summary-label">Stages</span>
            <span className="summary-value">{run.stages.length}</span>
          </div>
        </div>

        <h2 className="section-title">Ranked Opportunities</h2>

        {opportunities.length === 0 && (
          <p className="empty-msg">
            No opportunities ranked yet. Stage 4 may not have completed.
          </p>
        )}

        <div className="opp-list">
          {opportunities.map((opp) => (
            <OpportunityCard key={opp.index} opportunity={opp} runId={runId} />
          ))}
        </div>
      </main>

      <style jsx>{`
        .run-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }
        .run-header {
          display: flex;
          align-items: center;
          padding: 12px 24px;
          background: var(--bg-surface);
          box-shadow: var(--shadow-sm);
        }
        .header-left {
          display: flex;
          align-items: center;
          gap: 10px;
        }
        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }
        .breadcrumb {
          font-size: 14px;
          color: var(--text-secondary);
          text-decoration: none;
        }
        .breadcrumb:hover {
          color: var(--text-primary);
        }
        .breadcrumb-sep {
          color: var(--text-muted);
          font-size: 14px;
        }
        .page-title {
          font-size: 14px;
          font-weight: 600;
          font-family: var(--font-geist-mono);
          color: var(--text-primary);
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
        .run-content {
          flex: 1;
          padding: 24px;
          max-width: 900px;
          margin: 0 auto;
          width: 100%;
        }
        .run-summary {
          display: flex;
          gap: 24px;
          margin-bottom: 24px;
          padding: 16px;
          background: var(--bg-surface);
          border-radius: var(--radius-md);
          box-shadow: var(--shadow-sm);
        }
        .summary-item {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }
        .summary-label {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .summary-value {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
          text-transform: capitalize;
        }
        .section-title {
          font-size: 16px;
          font-weight: 600;
          margin: 0 0 16px;
          color: var(--text-primary);
        }
        .empty-msg {
          color: var(--text-secondary);
          font-size: 14px;
        }
        .opp-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .loading-container,
        .error-container {
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
        .error-container p {
          color: var(--accent-red);
        }
        .error-container a {
          color: var(--accent-blue);
        }
      `}</style>
    </div>
  );
}
