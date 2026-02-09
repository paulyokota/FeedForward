"use client";

import Link from "next/link";
import type { RankedOpportunity } from "@/lib/types";
import { REVIEW_DECISION_CONFIG } from "@/lib/types";
import type { ReviewDecisionType } from "@/lib/types";

export function OpportunityCard({
  opportunity,
  runId,
}: {
  opportunity: RankedOpportunity;
  runId: string;
}) {
  const reviewConfig = opportunity.review_status
    ? REVIEW_DECISION_CONFIG[opportunity.review_status as ReviewDecisionType]
    : null;

  return (
    <Link
      href={`/discovery/${runId}/${opportunity.index}`}
      className="opp-card"
    >
      <div className="opp-header">
        <span className="opp-rank">#{opportunity.recommended_rank}</span>
        <span className="opp-area">{opportunity.affected_area}</span>
        {reviewConfig && (
          <span className="opp-status" style={{ color: reviewConfig.color }}>
            {reviewConfig.label}
          </span>
        )}
        {!reviewConfig && <span className="opp-pending">Pending review</span>}
      </div>
      <p className="opp-problem">{opportunity.problem_statement}</p>
      <div className="opp-meta">
        <span>{opportunity.evidence_count} evidence</span>
        {opportunity.effort_estimate && (
          <span>{opportunity.effort_estimate}</span>
        )}
        {opportunity.build_experiment_decision && (
          <span className="opp-decision">
            {opportunity.build_experiment_decision.replace(/_/g, " ")}
          </span>
        )}
      </div>
      <p className="opp-rationale">{opportunity.rationale}</p>

      <style jsx>{`
        .opp-card {
          display: block;
          padding: 16px;
          background: var(--bg-surface);
          border-radius: var(--radius-md);
          text-decoration: none;
          color: var(--text-primary);
          transition: all 0.15s ease;
          box-shadow: var(--shadow-sm);
        }
        .opp-card:hover {
          box-shadow: var(--shadow-md);
          background: var(--bg-elevated);
        }
        .opp-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }
        .opp-rank {
          font-size: 14px;
          font-weight: 700;
          color: var(--accent-blue);
        }
        .opp-area {
          font-size: 12px;
          color: var(--text-tertiary);
          background: var(--bg-elevated);
          padding: 2px 8px;
          border-radius: 4px;
        }
        .opp-status {
          margin-left: auto;
          font-size: 12px;
          font-weight: 600;
        }
        .opp-pending {
          margin-left: auto;
          font-size: 12px;
          color: var(--text-muted);
        }
        .opp-problem {
          font-size: 14px;
          font-weight: 500;
          margin: 0 0 8px;
          line-height: 1.4;
        }
        .opp-meta {
          display: flex;
          gap: 12px;
          font-size: 12px;
          color: var(--text-tertiary);
          margin-bottom: 8px;
        }
        .opp-decision {
          text-transform: capitalize;
        }
        .opp-rationale {
          font-size: 13px;
          color: var(--text-secondary);
          margin: 0;
          line-height: 1.4;
        }
      `}</style>
    </Link>
  );
}
