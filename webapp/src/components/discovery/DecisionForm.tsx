"use client";

import { useState } from "react";
import type { ReviewDecisionRequest, ReviewDecisionType } from "@/lib/types";
import { REVIEW_DECISION_CONFIG } from "@/lib/types";

const DECISION_TYPES: ReviewDecisionType[] = [
  "accepted",
  "rejected",
  "deferred",
  "sent_back",
  "priority_adjusted",
];

export function DecisionForm({
  onSubmit,
  existingDecision,
}: {
  onSubmit: (decision: ReviewDecisionRequest) => Promise<void>;
  existingDecision?: Record<string, unknown> | null;
}) {
  const [decision, setDecision] = useState<ReviewDecisionType>(
    (existingDecision?.decision as ReviewDecisionType) || "accepted",
  );
  const [reasoning, setReasoning] = useState(
    (existingDecision?.reasoning as string) || "",
  );
  const [adjustedPriority, setAdjustedPriority] = useState<string>(
    existingDecision?.adjusted_priority
      ? String(existingDecision.adjusted_priority)
      : "",
  );
  const [sendBackStage, setSendBackStage] = useState(
    (existingDecision?.send_back_to_stage as string) || "",
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!reasoning.trim()) {
      setError("Reasoning is required");
      return;
    }

    const req: ReviewDecisionRequest = {
      decision,
      reasoning: reasoning.trim(),
    };

    if (decision === "priority_adjusted") {
      const parsed = parseInt(adjustedPriority, 10);
      if (isNaN(parsed) || parsed < 1) {
        setError("Adjusted priority must be a positive number");
        return;
      }
      req.adjusted_priority = parsed;
    }

    if (decision === "sent_back") {
      if (!sendBackStage.trim()) {
        setError("Target stage is required for send-back decisions");
        return;
      }
      req.send_back_to_stage = sendBackStage.trim();
    }

    setSubmitting(true);
    try {
      await onSubmit(req);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="decision-form" onSubmit={handleSubmit}>
      <h3>Review Decision</h3>

      <div className="decision-buttons">
        {DECISION_TYPES.map((type) => {
          const config = REVIEW_DECISION_CONFIG[type];
          return (
            <button
              key={type}
              type="button"
              className={`decision-btn ${decision === type ? "active" : ""}`}
              style={
                decision === type
                  ? { borderColor: config.color, color: config.color }
                  : undefined
              }
              onClick={() => setDecision(type)}
            >
              {config.label}
            </button>
          );
        })}
      </div>

      {decision === "priority_adjusted" && (
        <div className="form-field">
          <label>New priority rank</label>
          <input
            type="number"
            min="1"
            value={adjustedPriority}
            onChange={(e) => setAdjustedPriority(e.target.value)}
            placeholder="e.g. 1"
          />
        </div>
      )}

      {decision === "sent_back" && (
        <div className="form-field">
          <label>Send back to stage</label>
          <select
            value={sendBackStage}
            onChange={(e) => setSendBackStage(e.target.value)}
          >
            <option value="">Select stage...</option>
            <option value="exploration">Exploration</option>
            <option value="opportunity_framing">Opportunity Framing</option>
            <option value="solution_validation">Solution Validation</option>
            <option value="feasibility_risk">Feasibility + Risk</option>
            <option value="prioritization">Prioritization</option>
          </select>
        </div>
      )}

      <div className="form-field">
        <label>Reasoning</label>
        <textarea
          value={reasoning}
          onChange={(e) => setReasoning(e.target.value)}
          placeholder="Why this decision?"
          rows={3}
        />
      </div>

      {error && <p className="form-error">{error}</p>}

      <button
        type="submit"
        className="submit-btn"
        disabled={submitting || !reasoning.trim()}
      >
        {submitting ? "Submitting..." : "Submit Decision"}
      </button>

      <style jsx>{`
        .decision-form {
          background: var(--bg-surface);
          border-radius: var(--radius-md);
          padding: 20px;
          box-shadow: var(--shadow-sm);
        }
        .decision-form h3 {
          margin: 0 0 16px;
          font-size: 16px;
          font-weight: 600;
        }
        .decision-buttons {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          margin-bottom: 16px;
        }
        .decision-btn {
          padding: 8px 16px;
          border: 2px solid var(--border-default);
          border-radius: var(--radius-md);
          background: none;
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .decision-btn:hover {
          background: var(--bg-hover);
        }
        .decision-btn.active {
          background: var(--bg-elevated);
          font-weight: 600;
        }
        .form-field {
          margin-bottom: 12px;
        }
        .form-field label {
          display: block;
          font-size: 12px;
          font-weight: 500;
          color: var(--text-tertiary);
          margin-bottom: 4px;
        }
        .form-field input,
        .form-field select,
        .form-field textarea {
          width: 100%;
          padding: 8px 12px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-size: 13px;
          font-family: inherit;
        }
        .form-field input:focus,
        .form-field select:focus,
        .form-field textarea:focus {
          outline: 2px solid var(--accent-blue);
          outline-offset: -2px;
        }
        .form-field textarea {
          resize: vertical;
          min-height: 60px;
        }
        .form-error {
          color: var(--accent-red);
          font-size: 13px;
          margin: 0 0 12px;
        }
        .submit-btn {
          padding: 10px 24px;
          background: var(--accent-blue);
          color: white;
          border: none;
          border-radius: var(--radius-md);
          font-size: 14px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .submit-btn:hover:not(:disabled) {
          opacity: 0.9;
        }
        .submit-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
    </form>
  );
}
