"use client";

import { useState } from "react";

interface ArtifactSectionProps {
  title: string;
  stageName: string;
  data: Record<string, unknown> | null;
  defaultOpen?: boolean;
}

function ArtifactSection({
  title,
  stageName,
  data,
  defaultOpen = false,
}: ArtifactSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (!data) {
    return (
      <div className="artifact-section empty">
        <div className="artifact-header" onClick={() => setIsOpen(!isOpen)}>
          <span className="artifact-stage">{stageName}</span>
          <span className="artifact-title">{title}</span>
          <span className="artifact-empty-badge">Not available</span>
        </div>

        <style jsx>{`
          .artifact-section.empty {
            opacity: 0.5;
          }
          .artifact-header {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 12px 16px;
            cursor: pointer;
            border-radius: var(--radius-md);
          }
          .artifact-stage {
            font-size: 11px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            min-width: 80px;
          }
          .artifact-title {
            font-size: 14px;
            font-weight: 500;
            color: var(--text-primary);
          }
          .artifact-empty-badge {
            margin-left: auto;
            font-size: 11px;
            color: var(--text-muted);
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="artifact-section">
      <div className="artifact-header" onClick={() => setIsOpen(!isOpen)}>
        <span className="artifact-stage">{stageName}</span>
        <span className="artifact-title">{title}</span>
        <span className="artifact-toggle">{isOpen ? "\u25BC" : "\u25B6"}</span>
      </div>
      {isOpen && (
        <div className="artifact-body">
          <pre>{JSON.stringify(data, null, 2)}</pre>
        </div>
      )}

      <style jsx>{`
        .artifact-section {
          border-bottom: 1px solid var(--border-subtle);
        }
        .artifact-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 16px;
          cursor: pointer;
          border-radius: var(--radius-md);
          transition: background 0.1s ease;
        }
        .artifact-header:hover {
          background: var(--bg-hover);
        }
        .artifact-stage {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          min-width: 80px;
        }
        .artifact-title {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-primary);
        }
        .artifact-toggle {
          margin-left: auto;
          font-size: 10px;
          color: var(--text-muted);
        }
        .artifact-body {
          padding: 0 16px 16px;
        }
        .artifact-body pre {
          background: var(--bg-elevated);
          padding: 12px;
          border-radius: var(--radius-md);
          font-size: 12px;
          font-family: var(--font-geist-mono);
          overflow-x: auto;
          color: var(--text-secondary);
          margin: 0;
          line-height: 1.5;
        }
      `}</style>
    </div>
  );
}

export function ArtifactChain({
  detail,
}: {
  detail: {
    exploration: Record<string, unknown> | null;
    opportunity_brief: Record<string, unknown> | null;
    solution_brief: Record<string, unknown> | null;
    tech_spec: Record<string, unknown> | null;
    priority_rationale: Record<string, unknown> | null;
    review_decision: Record<string, unknown> | null;
  };
}) {
  return (
    <div className="artifact-chain">
      <ArtifactSection
        stageName="Stage 0"
        title="Exploration Findings"
        data={detail.exploration}
      />
      <ArtifactSection
        stageName="Stage 1"
        title="Opportunity Brief"
        data={detail.opportunity_brief}
        defaultOpen
      />
      <ArtifactSection
        stageName="Stage 2"
        title="Solution Brief"
        data={detail.solution_brief}
        defaultOpen
      />
      <ArtifactSection
        stageName="Stage 3"
        title="Technical Spec"
        data={detail.tech_spec}
      />
      <ArtifactSection
        stageName="Stage 4"
        title="Priority Rationale"
        data={detail.priority_rationale}
      />
      {detail.review_decision && (
        <ArtifactSection
          stageName="Stage 5"
          title="Review Decision"
          data={detail.review_decision}
          defaultOpen
        />
      )}

      <style jsx>{`
        .artifact-chain {
          background: var(--bg-surface);
          border-radius: var(--radius-md);
          overflow: hidden;
          box-shadow: var(--shadow-sm);
        }
      `}</style>
    </div>
  );
}
