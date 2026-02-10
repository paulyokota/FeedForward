"use client";

import { useState } from "react";

/* ─── Shared section wrapper ────────────────────────────────── */

function Section({
  stageName,
  title,
  defaultOpen = false,
  empty = false,
  children,
}: {
  stageName: string;
  title: string;
  defaultOpen?: boolean;
  empty?: boolean;
  children?: React.ReactNode;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  return (
    <div className={`section ${empty ? "empty" : ""}`}>
      <div className="section-header" onClick={() => setIsOpen(!isOpen)}>
        <span className="section-stage">{stageName}</span>
        <span className="section-title">{title}</span>
        {empty ? (
          <span className="section-badge">Not available</span>
        ) : (
          <span className="section-toggle">{isOpen ? "\u25BC" : "\u25B6"}</span>
        )}
      </div>
      {isOpen && !empty && <div className="section-body">{children}</div>}

      <style jsx>{`
        .section {
          border-bottom: 1px solid var(--border-subtle);
        }
        .section.empty {
          opacity: 0.5;
        }
        .section-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 12px 16px;
          cursor: pointer;
          border-radius: var(--radius-md);
          transition: background 0.1s ease;
        }
        .section-header:hover {
          background: var(--bg-hover);
        }
        .section-stage {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          min-width: 80px;
        }
        .section-title {
          font-size: 14px;
          font-weight: 500;
          color: var(--text-primary);
        }
        .section-toggle {
          margin-left: auto;
          font-size: 10px;
          color: var(--text-muted);
        }
        .section-badge {
          margin-left: auto;
          font-size: 11px;
          color: var(--text-muted);
        }
        .section-body {
          padding: 0 16px 16px;
        }
      `}</style>
    </div>
  );
}

/* ─── Small helpers ─────────────────────────────────────────── */

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="field">
      <dt>{label}</dt>
      <dd>{children}</dd>
      <style jsx>{`
        .field {
          margin-bottom: 12px;
        }
        dt {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          margin-bottom: 4px;
        }
        dd {
          margin: 0;
          font-size: 14px;
          line-height: 1.5;
          color: var(--text-primary);
        }
      `}</style>
    </div>
  );
}

function Badge({
  children,
  color,
}: {
  children: React.ReactNode;
  color?: string;
}) {
  return (
    <span className="badge" style={color ? { background: color } : undefined}>
      {children}
      <style jsx>{`
        .badge {
          display: inline-block;
          padding: 2px 8px;
          border-radius: 4px;
          font-size: 12px;
          font-weight: 500;
          background: var(--bg-elevated);
          color: var(--text-secondary);
        }
      `}</style>
    </span>
  );
}

const RISK_COLORS: Record<string, string> = {
  low: "hsla(140, 60%, 40%, 0.15)",
  medium: "hsla(40, 80%, 50%, 0.15)",
  high: "hsla(0, 70%, 50%, 0.15)",
};

const DECISION_LABELS: Record<string, string> = {
  build_now: "Build Now",
  experiment_first: "Experiment First",
  defer: "Defer",
  reject: "Reject",
};

/* ─── Try to parse a JSON string, return null if not valid ─── */

function tryParseJson(value: unknown): unknown | null {
  if (typeof value !== "string") return null;
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

/* ─── Stage-specific renderers ──────────────────────────────── */

function OpportunityBriefView({ data }: { data: Record<string, unknown> }) {
  const evidence = (data.evidence as Array<Record<string, unknown>>) || [];
  const sourceFindings = (data.source_findings as string[]) || [];

  return (
    <div>
      <Field label="Problem Statement">
        {(data.problem_statement as string) || "\u2014"}
      </Field>
      <Field label="Affected Area">
        <Badge>{(data.affected_area as string) || "\u2014"}</Badge>
      </Field>
      <Field label="Counterfactual">
        {(data.counterfactual as string) || "\u2014"}
      </Field>
      {sourceFindings.length > 0 && (
        <Field label="Source Findings">
          <ul className="finding-list">
            {sourceFindings.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </Field>
      )}
      {evidence.length > 0 && (
        <Field label="Evidence">
          <div className="evidence-chips">
            {Object.entries(
              evidence.reduce<
                Record<string, { high: number; med: number; low: number }>
              >((acc, ev) => {
                const src = (ev.source_type as string) || "unknown";
                if (!acc[src]) acc[src] = { high: 0, med: 0, low: 0 };
                const conf = (ev.confidence as string) || "";
                if (conf === "high") acc[src].high++;
                else if (conf === "medium") acc[src].med++;
                else acc[src].low++;
                return acc;
              }, {}),
            ).map(([src, counts]) => {
              const parts = [];
              if (counts.high) parts.push(`${counts.high} high`);
              if (counts.med) parts.push(`${counts.med} med`);
              if (counts.low) parts.push(`${counts.low} low`);
              const total = counts.high + counts.med + counts.low;
              return (
                <Badge key={src}>
                  {src}&times;{total}{" "}
                  <span className="evidence-conf">({parts.join(", ")})</span>
                </Badge>
              );
            })}
          </div>
        </Field>
      )}
      {data.explorer_coverage != null && (
        <Field label="Explorer Coverage">
          {String(data.explorer_coverage)}
        </Field>
      )}

      <style jsx>{`
        .finding-list {
          margin: 4px 0 0;
          padding-left: 20px;
        }
        .finding-list li {
          margin-bottom: 4px;
          font-size: 14px;
          color: var(--text-secondary);
        }
        .evidence-chips {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }
        .evidence-conf {
          color: var(--text-muted);
          font-size: 11px;
        }
      `}</style>
    </div>
  );
}

function SolutionBriefView({ data }: { data: Record<string, unknown> }) {
  const decision = (data.build_experiment_decision as string) || "";
  const parsed = tryParseJson(data.proposed_solution);
  const challenges =
    (data.validation_challenges as Array<Record<string, unknown>>) || [];

  // success_metrics can be a string (JSON) or object
  let metricsDisplay: string | null = null;
  if (data.success_metrics) {
    if (typeof data.success_metrics === "string") {
      metricsDisplay = data.success_metrics;
    } else {
      metricsDisplay = JSON.stringify(data.success_metrics, null, 2);
    }
  }

  // Parse components from proposed_solution if it's a JSON string
  const components =
    parsed &&
    typeof parsed === "object" &&
    "components" in (parsed as Record<string, unknown>)
      ? ((parsed as Record<string, unknown>).components as Array<
          Record<string, string>
        >)
      : null;

  // Key risk teaser from final validation challenge
  const lastChallenge =
    challenges.length > 0 ? challenges[challenges.length - 1] : null;
  const riskTeaser = lastChallenge
    ? String(lastChallenge.critique || lastChallenge.challenge_reason || "")
    : "";

  return (
    <div>
      <Field label="Decision">
        <Badge>{DECISION_LABELS[decision] || decision}</Badge>
      </Field>

      {riskTeaser && (
        <Field label="Key Risk">
          <span className="risk-teaser">{riskTeaser}</span>
        </Field>
      )}

      {components ? (
        <Field label="Proposed Solution">
          <div className="components">
            {components.map((c, i) => (
              <div key={i} className="component">
                <strong>{c.name}</strong>
                <p>{c.description}</p>
              </div>
            ))}
          </div>
        </Field>
      ) : data.proposed_solution ? (
        <Field label="Proposed Solution">
          {typeof data.proposed_solution === "string"
            ? data.proposed_solution
            : JSON.stringify(data.proposed_solution)}
        </Field>
      ) : null}

      {data.experiment_plan != null && (
        <Field label="Experiment Plan">{String(data.experiment_plan)}</Field>
      )}

      {metricsDisplay && (
        <Field label="Success Metrics">
          <pre className="metrics-pre">{metricsDisplay}</pre>
        </Field>
      )}

      {challenges.length > 0 && (
        <Field label="Validation Challenges">
          {challenges.map((ch, i) => (
            <div key={i} className="challenge">
              <span className="challenge-round">
                Round {ch.round as number}
              </span>
              <p>{ch.critique as string}</p>
            </div>
          ))}
        </Field>
      )}

      <style jsx>{`
        .components {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 4px;
        }
        .component {
          background: var(--bg-elevated);
          padding: 10px 12px;
          border-radius: var(--radius-md);
        }
        .component strong {
          font-size: 13px;
        }
        .component p {
          margin: 4px 0 0;
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
        .metrics-pre {
          background: var(--bg-elevated);
          padding: 8px 12px;
          border-radius: var(--radius-md);
          font-size: 12px;
          font-family: var(--font-geist-mono);
          overflow-x: auto;
          color: var(--text-secondary);
          margin: 4px 0 0;
          line-height: 1.5;
          white-space: pre-wrap;
        }
        .challenge {
          background: var(--bg-elevated);
          padding: 10px 12px;
          border-radius: var(--radius-md);
          margin-top: 6px;
        }
        .challenge-round {
          font-size: 11px;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
        }
        .challenge p {
          margin: 4px 0 0;
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
        .risk-teaser {
          font-size: 13px;
          color: var(--text-secondary);
          font-style: italic;
        }
      `}</style>
    </div>
  );
}

function TechSpecView({ data }: { data: Record<string, unknown> }) {
  const risks = (data.risks as Array<Record<string, string>>) || [];
  const riskLevel = (data.overall_risk_level as string) || "";

  // Parse approach if it's a JSON string with components
  const parsed = tryParseJson(data.approach);
  const components =
    parsed &&
    typeof parsed === "object" &&
    "components" in (parsed as Record<string, unknown>)
      ? ((parsed as Record<string, unknown>).components as Array<
          Record<string, string>
        >)
      : null;

  return (
    <div>
      <div className="spec-topline">
        <Field label="Feasibility">
          <Badge color="hsla(140, 60%, 40%, 0.15)">Feasible</Badge>
        </Field>
        <Field label="Effort Estimate">
          {(data.effort_estimate as string) || "\u2014"}
        </Field>
        <Field label="Risk Level">
          <Badge color={RISK_COLORS[riskLevel]}>{riskLevel || "\u2014"}</Badge>
        </Field>
      </div>

      {components ? (
        <Field label="Technical Approach">
          <div className="components">
            {components.map((c, i) => (
              <div key={i} className="component">
                <strong>{c.name}</strong>
                <p>{c.description}</p>
              </div>
            ))}
          </div>
        </Field>
      ) : data.approach ? (
        <Field label="Technical Approach">
          {typeof data.approach === "string"
            ? data.approach
            : JSON.stringify(data.approach)}
        </Field>
      ) : null}

      {data.acceptance_criteria != null && (
        <Field label="Acceptance Criteria">
          {String(data.acceptance_criteria)}
        </Field>
      )}

      {risks.length > 0 && (
        <Field label={`Risks (${risks.length})`}>
          <div className="risk-list">
            {risks.map((r, i) => (
              <div key={i} className="risk-item">
                <div className="risk-header">
                  <Badge color={RISK_COLORS[r.severity]}>{r.severity}</Badge>
                  <span className="risk-desc">{r.description}</span>
                </div>
                <p className="risk-mitigation">{r.mitigation}</p>
              </div>
            ))}
          </div>
        </Field>
      )}

      {data.dependencies != null && (
        <Field label="Dependencies">{String(data.dependencies)}</Field>
      )}

      {data.rollout_concerns != null && (
        <Field label="Rollout Concerns">{String(data.rollout_concerns)}</Field>
      )}

      <style jsx>{`
        .spec-topline {
          display: flex;
          gap: 24px;
        }
        .components {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 4px;
        }
        .component {
          background: var(--bg-elevated);
          padding: 10px 12px;
          border-radius: var(--radius-md);
        }
        .component strong {
          font-size: 13px;
        }
        .component p {
          margin: 4px 0 0;
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
        .risk-list {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-top: 4px;
        }
        .risk-item {
          background: var(--bg-elevated);
          padding: 10px 12px;
          border-radius: var(--radius-md);
        }
        .risk-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .risk-desc {
          font-size: 13px;
          font-weight: 500;
        }
        .risk-mitigation {
          margin: 6px 0 0;
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.4;
        }
      `}</style>
    </div>
  );
}

function PriorityRationaleView({ data }: { data: Record<string, unknown> }) {
  const flags = (data.flags as string[]) || [];
  const deps = (data.dependencies as string[]) || [];

  return (
    <div>
      <Field label="Recommended Rank">
        <span className="rank">#{data.recommended_rank as number}</span>
      </Field>
      <Field label="Rationale">{(data.rationale as string) || "\u2014"}</Field>
      {flags.length > 0 && (
        <Field label="Flags">
          <div className="badge-row">
            {flags.map((f, i) => (
              <Badge key={i}>{f}</Badge>
            ))}
          </div>
        </Field>
      )}
      {deps.length > 0 && (
        <Field label="Dependencies">
          <div className="badge-row">
            {deps.map((d, i) => (
              <Badge key={i}>{d}</Badge>
            ))}
          </div>
        </Field>
      )}

      <style jsx>{`
        .rank {
          font-size: 20px;
          font-weight: 700;
          color: var(--accent-blue);
        }
        .badge-row {
          display: flex;
          gap: 6px;
          flex-wrap: wrap;
        }
      `}</style>
    </div>
  );
}

/* ─── Exploration view with signal mix summary ─────────────── */

function ExplorationView({ data }: { data: Record<string, unknown> }) {
  const findings = (data.findings as Array<Record<string, unknown>>) || [];

  // Count evidence by source_type across all findings
  const sourceCounts: Record<string, number> = {};
  for (const f of findings) {
    const evidence = (f.evidence as Array<Record<string, unknown>>) || [];
    for (const ev of evidence) {
      const src = (ev.source_type as string) || "unknown";
      sourceCounts[src] = (sourceCounts[src] || 0) + 1;
    }
  }

  const signalMix = Object.entries(sourceCounts)
    .sort(([, a], [, b]) => b - a)
    .map(([src, count]) => `${src} ${count}`)
    .join(" \u00B7 ");

  return (
    <div>
      <Field label={`${findings.length} Findings`}>
        {signalMix || "No evidence sources"}
      </Field>
      <RawJsonView data={data} />
    </div>
  );
}

/* ─── Fallback: raw JSON ───────────────────────────────────── */

function RawJsonView({ data }: { data: Record<string, unknown> }) {
  return (
    <pre className="raw-json">
      {JSON.stringify(data, null, 2)}
      <style jsx>{`
        .raw-json {
          background: var(--bg-elevated);
          padding: 12px;
          border-radius: var(--radius-md);
          font-size: 12px;
          font-family: var(--font-geist-mono);
          overflow-x: auto;
          color: var(--text-secondary);
          margin: 0;
          line-height: 1.5;
          max-height: 400px;
          overflow-y: auto;
        }
      `}</style>
    </pre>
  );
}

/* ─── Main export ───────────────────────────────────────────── */

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
      <Section
        stageName="Stage 0"
        title="Exploration Findings"
        empty={!detail.exploration}
      >
        {detail.exploration && <ExplorationView data={detail.exploration} />}
      </Section>

      <Section
        stageName="Stage 1"
        title="Opportunity Brief"
        defaultOpen
        empty={!detail.opportunity_brief}
      >
        {detail.opportunity_brief && (
          <OpportunityBriefView data={detail.opportunity_brief} />
        )}
      </Section>

      <Section
        stageName="Stage 2"
        title="Solution Brief"
        defaultOpen
        empty={!detail.solution_brief}
      >
        {detail.solution_brief && (
          <SolutionBriefView data={detail.solution_brief} />
        )}
      </Section>

      <Section
        stageName="Stage 3"
        title="Technical Spec"
        empty={!detail.tech_spec}
      >
        {detail.tech_spec && <TechSpecView data={detail.tech_spec} />}
      </Section>

      <Section
        stageName="Stage 4"
        title="Priority Rationale"
        empty={!detail.priority_rationale}
      >
        {detail.priority_rationale && (
          <PriorityRationaleView data={detail.priority_rationale} />
        )}
      </Section>

      {detail.review_decision && (
        <Section stageName="Stage 5" title="Review Decision" defaultOpen>
          <RawJsonView data={detail.review_decision} />
        </Section>
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
