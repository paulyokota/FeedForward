"use client";

import type { Story, SortKey } from "@/lib/types";
import { PRIORITY_CONFIG, getSyncState, SORT_CONFIG } from "@/lib/types";
import Link from "next/link";
import React from "react";
import { EvidenceBadge } from "./EvidenceBadge";
import { SyncStatusBadge } from "./SyncStatusBadge";

// Extended Story type to include optional sync_status from board API
interface StoryWithSync extends Story {
  sync_status?: string | null;
}

interface StoryCardProps {
  story: StoryWithSync;
  isDragOverlay?: boolean;
  style?: React.CSSProperties;
  sortBy?: SortKey;
}

// Score fields that can be displayed as badges
// Note: Must be updated if new score fields are added to SortKey
type ScoreSortKey =
  | "confidence_score"
  | "actionability_score"
  | "fix_size_score"
  | "severity_score"
  | "churn_risk_score";

const SCORE_FIELDS: ScoreSortKey[] = [
  "confidence_score",
  "actionability_score",
  "fix_size_score",
  "severity_score",
  "churn_risk_score",
];

function isScoreField(key: SortKey): key is ScoreSortKey {
  return (SCORE_FIELDS as string[]).includes(key);
}

// Get score value and label for the active sort dimension
function getActiveScore(
  story: StoryWithSync,
  sortBy?: SortKey,
): { value: number | null; label: string } | null {
  if (!sortBy || !isScoreField(sortBy)) return null;

  // Type-safe score access via explicit mapping
  const value = story[sortBy];
  const label = SORT_CONFIG[sortBy].label;
  return { value, label };
}

export const StoryCard = React.forwardRef<HTMLElement, StoryCardProps>(
  function StoryCard(
    { story, isDragOverlay = false, style, sortBy, ...props },
    ref,
  ) {
    const priorityConfig = story.priority
      ? PRIORITY_CONFIG[story.priority]
      : null;
    const syncState = getSyncState(story.sync_status);
    const activeScore = getActiveScore(story, sortBy);

    const cardContent = (
      <article
        ref={ref}
        className="story-card"
        style={style}
        aria-label={`Story: ${story.title}`}
        {...props}
      >
        <div className="card-header">
          <h3 className="card-title">{story.title}</h3>
          {priorityConfig && (
            <span
              className="priority-badge"
              style={{
                backgroundColor: `${priorityConfig.color}20`,
                color: priorityConfig.color,
              }}
            >
              {priorityConfig.label}
            </span>
          )}
        </div>

        {story.product_area && (
          <span className="product-area">{story.product_area}</span>
        )}

        <div className="card-meta">
          <div className="meta-item" title="Evidence count">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            <span>{story.evidence_count}</span>
          </div>

          <div className="meta-item" title="Conversations">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            </svg>
            <span>{story.conversation_count}</span>
          </div>

          {/* Sync status indicator */}
          <div
            className="meta-item sync-indicator"
            title={`Sync: ${syncState}`}
          >
            <SyncStatusBadge state={syncState} size="sm" />
          </div>

          {/* Low evidence warning - Issue #197 */}
          <EvidenceBadge excerptCount={story.excerpt_count} size="sm" />

          {/* Active sort score badge - shows % for consistency with confidence */}
          {activeScore && activeScore.value !== null && (
            <div className="meta-item score-badge" title={activeScore.label}>
              <span className="score-label">{activeScore.label}</span>
              <span className="score-value">
                {Math.round(activeScore.value)}%
              </span>
            </div>
          )}

          {/* Fallback: show confidence if no active sort score */}
          {!activeScore && story.confidence_score !== null && (
            <div className="meta-item confidence" title="Confidence score">
              <span className="confidence-value">
                {Math.round(story.confidence_score)}%
              </span>
            </div>
          )}
        </div>

        <style jsx>{`
          .story-card {
            display: block;
            padding: 14px 16px;
            cursor: pointer;
            text-decoration: none;
            color: inherit;
          }

          .card-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 10px;
            margin-bottom: 10px;
          }

          .card-title {
            font-size: 13px;
            font-weight: 500;
            color: var(--text-primary);
            line-height: 1.45;
            margin: 0;
            flex: 1;
          }

          .priority-badge {
            font-size: 10px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            padding: 3px 8px;
            border-radius: 4px;
            flex-shrink: 0;
          }

          .product-area {
            display: inline-block;
            font-size: 11px;
            color: var(--text-secondary);
            background: var(--bg-elevated);
            padding: 3px 8px;
            border-radius: 4px;
            margin-bottom: 12px;
          }

          .card-meta {
            display: flex;
            align-items: center;
            gap: 14px;
          }

          .meta-item {
            display: flex;
            align-items: center;
            gap: 5px;
            font-size: 12px;
            color: var(--text-secondary);
          }

          .meta-item svg {
            opacity: 0.8;
          }

          .confidence {
            margin-left: auto;
          }

          .confidence-value {
            font-size: 11px;
            font-weight: 600;
            color: var(--accent-green);
          }

          .score-badge {
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 4px;
            background: var(--bg-elevated);
            padding: 2px 8px;
            border-radius: 4px;
          }

          .score-label {
            font-size: 10px;
            color: var(--text-tertiary);
            text-transform: uppercase;
            letter-spacing: 0.3px;
          }

          .score-value {
            font-size: 11px;
            font-weight: 600;
            color: var(--accent-blue);
          }
        `}</style>
      </article>
    );

    // When used as drag overlay, don't wrap in Link
    if (isDragOverlay) {
      return cardContent;
    }

    return <Link href={`/story/${story.id}`}>{cardContent}</Link>;
  },
);
