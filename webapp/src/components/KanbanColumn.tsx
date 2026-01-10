"use client";

import type { Story, StatusKey } from "@/lib/types";
import { STATUS_CONFIG } from "@/lib/types";
import { StoryCard } from "./StoryCard";

interface KanbanColumnProps {
  status: StatusKey;
  stories: Story[];
}

export function KanbanColumn({ status, stories }: KanbanColumnProps) {
  const config = STATUS_CONFIG[status];

  return (
    <div className="kanban-column">
      <div className="column-header">
        <div
          className="status-indicator"
          style={{ backgroundColor: config.color }}
        />
        <h2 className="column-title">{config.label}</h2>
        <span className="story-count">{stories.length}</span>
      </div>

      <div className="column-content stagger-children">
        {stories.map((story) => (
          <StoryCard key={story.id} story={story} />
        ))}
        {stories.length === 0 && <div className="empty-state">No stories</div>}
      </div>

      <style jsx>{`
        .kanban-column {
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
        }

        .column-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 16px;
          position: sticky;
          top: 0;
          background: var(--bg-primary);
          z-index: 1;
          border-radius: var(--radius-lg) var(--radius-lg) 0 0;
        }

        .status-indicator {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          box-shadow: 0 0 8px currentColor;
        }

        .column-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .story-count {
          font-size: 12px;
          font-weight: 500;
          color: var(--text-secondary);
          background: var(--bg-surface);
          padding: 2px 8px;
          border-radius: 10px;
          margin-left: auto;
        }

        .column-content {
          flex: 1;
          padding: 10px;
          display: flex;
          flex-direction: column;
          gap: 8px;
          overflow-y: auto;
          min-height: 200px;
        }

        .empty-state {
          color: var(--text-muted);
          font-size: 13px;
          text-align: center;
          padding: 32px 16px;
          border: 1px dashed var(--border-subtle);
          border-radius: var(--radius-md);
          margin: 8px;
        }
      `}</style>
    </div>
  );
}
