"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { OpportunityDetail, ReviewDecisionRequest } from "@/lib/types";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import { ArtifactChain } from "@/components/discovery/ArtifactChain";
import { DecisionForm } from "@/components/discovery/DecisionForm";

export default function OpportunityDetailPage() {
  const params = useParams();
  const router = useRouter();
  const runId = params.runId as string;
  const idx = parseInt(params.idx as string, 10);

  const [detail, setDetail] = useState<OpportunityDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.discovery
      .getOpportunityDetail(runId, idx)
      .then(setDetail)
      .catch((err) =>
        setError(err instanceof Error ? err.message : "Failed to load"),
      )
      .finally(() => setLoading(false));
  }, [runId, idx]);

  const handleSubmitDecision = useCallback(
    async (decision: ReviewDecisionRequest) => {
      await api.discovery.submitDecision(runId, idx, decision);
      // Refresh the detail to show the decision
      const updated = await api.discovery.getOpportunityDetail(runId, idx);
      setDetail(updated);
    },
    [runId, idx],
  );

  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <span>Loading opportunity...</span>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="error-container">
        <p>{error || "Opportunity not found"}</p>
        <Link href={`/discovery/${runId}`}>Back to run</Link>
      </div>
    );
  }

  const problemStatement =
    (detail.opportunity_brief?.problem_statement as string) || "Untitled";

  return (
    <div className="detail-layout">
      <header className="detail-header">
        <div className="header-left">
          <Link href="/">
            <FeedForwardLogo size="sm" />
          </Link>
          <div className="header-divider" />
          <Link href="/discovery" className="breadcrumb">
            Discovery
          </Link>
          <span className="breadcrumb-sep">/</span>
          <Link href={`/discovery/${runId}`} className="breadcrumb">
            {runId.slice(0, 8)}...
          </Link>
          <span className="breadcrumb-sep">/</span>
          <span className="page-title">Opportunity #{idx}</span>
        </div>
      </header>

      <main className="detail-content">
        <h1 className="opp-title">{problemStatement}</h1>

        <ArtifactChain detail={detail} />

        <div className="decision-section">
          <DecisionForm
            onSubmit={handleSubmitDecision}
            existingDecision={detail.review_decision}
          />
        </div>
      </main>

      <style jsx>{`
        .detail-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }
        .detail-header {
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
          color: var(--text-primary);
        }
        .detail-content {
          flex: 1;
          padding: 24px;
          max-width: 900px;
          margin: 0 auto;
          width: 100%;
        }
        .opp-title {
          font-size: 20px;
          font-weight: 600;
          margin: 0 0 24px;
          color: var(--text-primary);
          line-height: 1.3;
        }
        .decision-section {
          margin-top: 24px;
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
