"use client";

import { ThemeTrendResponse } from "@/lib/types";
import React from "react";

interface TrendingListProps {
  themes: ThemeTrendResponse[];
  maxItems?: number;
  onThemeClick?: (signature: string) => void;
}

export function TrendingList({
  themes,
  maxItems = 10,
  onThemeClick,
}: TrendingListProps) {
  const displayThemes = themes.slice(0, maxItems);

  const getTrendIcon = (direction: ThemeTrendResponse["trend_direction"]) => {
    switch (direction) {
      case "rising":
        return { icon: "\u2191", className: "trend-rising" };
      case "declining":
        return { icon: "\u2193", className: "trend-declining" };
      default:
        return { icon: "\u2192", className: "trend-stable" };
    }
  };

  if (displayThemes.length === 0) {
    return (
      <div className="trending-empty">
        <span>No trending themes</span>
        <style jsx>{`
          .trending-empty {
            padding: 24px;
            text-align: center;
            color: var(--text-tertiary);
            font-size: 13px;
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="trending-list">
      {displayThemes.map((theme, index) => {
        const trend = getTrendIcon(theme.trend_direction);
        const isClickable = !!onThemeClick;

        return (
          <div
            key={theme.theme_signature}
            className={`trending-item ${isClickable ? "clickable" : ""}`}
            onClick={() => onThemeClick?.(theme.theme_signature)}
            role={isClickable ? "button" : undefined}
            tabIndex={isClickable ? 0 : undefined}
            onKeyDown={(e) => {
              if (isClickable && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                onThemeClick?.(theme.theme_signature);
              }
            }}
          >
            <span className="rank">{index + 1}</span>

            <div className="theme-info">
              <div className="theme-signature">{theme.theme_signature}</div>
              {theme.product_area && (
                <span className="product-area">{theme.product_area}</span>
              )}
            </div>

            <div className="theme-stats">
              <span className="occurrence-count">{theme.occurrence_count}</span>
              <span className={`trend-indicator ${trend.className}`}>
                {trend.icon}
              </span>
            </div>
          </div>
        );
      })}

      <style jsx>{`
        .trending-list {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .trending-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 10px 12px;
          border-radius: var(--radius-md);
          transition:
            background-color 0.15s ease,
            transform 0.15s ease;
        }

        .trending-item.clickable {
          cursor: pointer;
        }

        .trending-item.clickable:hover {
          background: var(--bg-elevated);
        }

        .trending-item.clickable:active {
          transform: scale(0.99);
        }

        :global([data-theme="light"]) .trending-item.clickable:hover {
          background: var(--bg-hover);
        }

        .rank {
          width: 24px;
          height: 24px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 12px;
          font-weight: 600;
          color: var(--text-tertiary);
          background: var(--bg-surface);
          border-radius: var(--radius-sm);
          flex-shrink: 0;
        }

        :global([data-theme="light"]) .rank {
          background: var(--bg-hover);
        }

        .theme-info {
          flex: 1;
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .theme-signature {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
          line-height: 1.3;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .product-area {
          display: inline-block;
          font-size: 10px;
          font-weight: 500;
          color: var(--text-tertiary);
          background: var(--bg-elevated);
          padding: 2px 6px;
          border-radius: 3px;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          width: fit-content;
        }

        :global([data-theme="light"]) .product-area {
          background: var(--bg-hover);
        }

        .theme-stats {
          display: flex;
          align-items: center;
          gap: 8px;
          flex-shrink: 0;
        }

        .occurrence-count {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-secondary);
          font-variant-numeric: tabular-nums;
          min-width: 28px;
          text-align: right;
        }

        .trend-indicator {
          font-size: 16px;
          font-weight: 600;
          width: 18px;
          text-align: center;
        }

        .trend-rising {
          color: var(--accent-green);
        }

        .trend-declining {
          color: var(--accent-red);
        }

        .trend-stable {
          color: var(--text-tertiary);
        }
      `}</style>
    </div>
  );
}
