"use client";

import React from "react";

interface MetricCardProps {
  label: string;
  value: number | string;
  delta?: number;
  deltaLabel?: string;
  icon?: React.ReactNode;
}

export function MetricCard({
  label,
  value,
  delta,
  deltaLabel,
  icon,
}: MetricCardProps) {
  const hasDelta = typeof delta === "number";
  const isPositive = hasDelta && delta > 0;
  const isNegative = hasDelta && delta < 0;

  return (
    <div className="metric-card">
      <div className="metric-header">
        {icon && <div className="metric-icon">{icon}</div>}
        <span className="metric-label">{label}</span>
      </div>

      <div className="metric-value">{value}</div>

      {hasDelta && (
        <div
          className={`metric-delta ${isPositive ? "positive" : ""} ${isNegative ? "negative" : ""}`}
        >
          <span className="delta-arrow">
            {isPositive ? "\u2191" : isNegative ? "\u2193" : "\u2192"}
          </span>
          <span className="delta-value">
            {isPositive ? "+" : ""}
            {delta}
            {deltaLabel ? ` ${deltaLabel}` : ""}
          </span>
        </div>
      )}

      <style jsx>{`
        .metric-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border-radius: var(--radius-lg);
          padding: 16px 18px;
          box-shadow: var(--shadow-sm);
          transition:
            transform 0.2s ease,
            box-shadow 0.2s ease;
        }

        .metric-card:hover {
          transform: translateY(-1px);
          box-shadow: var(--shadow-md);
        }

        :global([data-theme="light"]) .metric-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .metric-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 8px;
        }

        .metric-icon {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 24px;
          height: 24px;
          color: var(--accent-teal);
          opacity: 0.9;
        }

        .metric-icon :global(svg) {
          width: 18px;
          height: 18px;
        }

        .metric-label {
          font-size: 12px;
          font-weight: 500;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .metric-value {
          font-size: 28px;
          font-weight: 600;
          color: var(--text-primary);
          line-height: 1.2;
          margin-bottom: 4px;
        }

        .metric-delta {
          display: flex;
          align-items: center;
          gap: 4px;
          font-size: 12px;
          font-weight: 500;
          color: var(--text-tertiary);
        }

        .metric-delta.positive {
          color: var(--accent-green);
        }

        .metric-delta.negative {
          color: var(--accent-red);
        }

        .delta-arrow {
          font-size: 14px;
        }

        .delta-value {
          font-variant-numeric: tabular-nums;
        }
      `}</style>
    </div>
  );
}
