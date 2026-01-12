"use client";

import React from "react";

interface DonutChartDataItem {
  label: string;
  value: number;
  color: string;
}

interface DonutChartProps {
  data: DonutChartDataItem[];
  size?: number;
  strokeWidth?: number;
  showLegend?: boolean;
}

export function DonutChart({
  data,
  size = 120,
  strokeWidth = 16,
  showLegend = true,
}: DonutChartProps) {
  const total = data.reduce((sum, item) => sum + item.value, 0);
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;

  // Calculate arc segments
  let accumulatedOffset = 0;
  const segments = data.map((item) => {
    const percentage = total > 0 ? item.value / total : 0;
    const dashLength = percentage * circumference;
    const dashOffset = circumference - accumulatedOffset;
    accumulatedOffset += dashLength;

    return {
      ...item,
      percentage,
      dashLength,
      dashOffset,
    };
  });

  return (
    <div className="donut-chart-container">
      <div className="donut-chart">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="donut-svg"
        >
          {/* Background circle */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="var(--bg-elevated)"
            strokeWidth={strokeWidth}
          />

          {/* Data segments - rendered in reverse order so first item appears on top */}
          {segments
            .slice()
            .reverse()
            .map((segment, index) => (
              <circle
                key={segment.label}
                cx={center}
                cy={center}
                r={radius}
                fill="none"
                stroke={segment.color}
                strokeWidth={strokeWidth}
                strokeDasharray={`${segment.dashLength} ${circumference}`}
                strokeDashoffset={segment.dashOffset}
                strokeLinecap="round"
                transform={`rotate(-90 ${center} ${center})`}
                className="donut-segment"
                style={{
                  animationDelay: `${(segments.length - 1 - index) * 100}ms`,
                }}
              />
            ))}

          {/* Center text */}
          <text
            x={center}
            y={center}
            textAnchor="middle"
            dominantBaseline="central"
            className="donut-center-text"
          >
            <tspan x={center} dy="-0.2em" className="donut-total">
              {total}
            </tspan>
            <tspan x={center} dy="1.4em" className="donut-label">
              total
            </tspan>
          </text>
        </svg>
      </div>

      {showLegend && (
        <div className="donut-legend">
          {data.map((item) => (
            <div key={item.label} className="legend-item">
              <span
                className="legend-dot"
                style={{ backgroundColor: item.color }}
              />
              <span className="legend-label">{item.label}</span>
              <span className="legend-value">{item.value}</span>
            </div>
          ))}
        </div>
      )}

      <style jsx>{`
        .donut-chart-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 16px;
        }

        .donut-chart {
          position: relative;
        }

        .donut-svg {
          display: block;
        }

        .donut-segment {
          transition:
            stroke-dasharray 0.5s ease,
            stroke-dashoffset 0.5s ease;
          animation: segmentReveal 0.6s ease forwards;
          opacity: 0;
        }

        @keyframes segmentReveal {
          from {
            opacity: 0;
            stroke-dasharray: 0 ${circumference};
          }
          to {
            opacity: 1;
          }
        }

        .donut-center-text {
          font-family: var(--font-sans);
        }

        .donut-total {
          font-size: 22px;
          font-weight: 600;
          fill: var(--text-primary);
        }

        .donut-label {
          font-size: 11px;
          font-weight: 500;
          fill: var(--text-tertiary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .donut-legend {
          display: flex;
          flex-wrap: wrap;
          justify-content: center;
          gap: 12px 16px;
          max-width: 200px;
        }

        .legend-item {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 12px;
        }

        .legend-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          flex-shrink: 0;
        }

        .legend-label {
          color: var(--text-secondary);
          white-space: nowrap;
        }

        .legend-value {
          font-weight: 600;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }
      `}</style>
    </div>
  );
}
