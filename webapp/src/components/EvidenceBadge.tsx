"use client";

import { EVIDENCE_QUALITY } from "@/lib/types";

interface EvidenceBadgeProps {
  excerptCount: number;
  size?: "sm" | "md";
  showLabel?: boolean;
}

/**
 * Badge indicating low evidence quality for a story.
 * Only renders when excerpt_count is below the LOW_THRESHOLD.
 *
 * Issue #197: Raise story evidence quality
 */
export function EvidenceBadge({
  excerptCount,
  size = "sm",
  showLabel = true,
}: EvidenceBadgeProps) {
  // Validate excerptCount is a valid number (handles null/undefined/NaN from API)
  const validCount =
    typeof excerptCount === "number" && !isNaN(excerptCount) ? excerptCount : 0;
  const isLow = validCount < EVIDENCE_QUALITY.LOW_THRESHOLD;

  // Don't render anything if evidence is sufficient
  if (!isLow) return null;

  const dotSize = size === "sm" ? 6 : 8;

  return (
    <div
      className="evidence-badge"
      title={`Low evidence: ${validCount} excerpt${validCount !== 1 ? "s" : ""}`}
    >
      <span
        className="evidence-dot"
        style={{
          width: dotSize,
          height: dotSize,
          backgroundColor: "var(--accent-amber)",
        }}
      />
      {showLabel && <span className="evidence-label">Low evidence</span>}

      <style jsx>{`
        .evidence-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
        }

        .evidence-dot {
          border-radius: 50%;
          flex-shrink: 0;
        }

        .evidence-label {
          font-size: ${size === "sm" ? "11px" : "12px"};
          font-weight: 500;
          color: var(--accent-amber);
        }
      `}</style>
    </div>
  );
}
