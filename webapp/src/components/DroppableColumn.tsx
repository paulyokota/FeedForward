"use client";

import { useDroppable } from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import type { Story, StatusKey } from "@/lib/types";
import { STATUS_CONFIG } from "@/lib/types";
import {
  createDroppableId,
  createDraggableId,
  type DroppableData,
  type DraggableData,
} from "@/lib/dnd.types";
import { StoryCard } from "./StoryCard";
import { useDragContext } from "./DndBoardProvider";

interface DroppableColumnProps {
  status: StatusKey;
  stories: Story[];
}

interface SortableStoryCardProps {
  story: Story;
  sourceColumn: StatusKey;
  index: number;
}

function SortableStoryCard({
  story,
  sourceColumn,
  index,
}: SortableStoryCardProps) {
  const { draggedCardHeight, isDragging: isAnyDragging } = useDragContext();
  const { attributes, listeners, setNodeRef, isDragging, isOver } = useSortable(
    {
      id: createDraggableId(story.id),
      data: {
        type: "story",
        story,
        sourceColumn,
        index,
      } as DraggableData,
      // Disable dnd-kit's built-in animations - we handle visual feedback ourselves
      transition: null,
    },
  );

  const showIndicator = isOver && !isDragging;

  // Don't use dnd-kit transforms - our indicator handles visual feedback
  const style: React.CSSProperties = {
    // Explicitly disable any transforms dnd-kit might apply
    transform: "none",
    ...(isDragging && {
      height: 0,
      minHeight: 0,
      overflow: "hidden",
      opacity: 0,
      margin: 0,
      padding: 0,
    }),
    cursor: isDragging ? "grabbing" : "grab",
    touchAction: "none",
  };

  // Always render indicator, animate height to make cards slide smoothly
  // Only show during active drag, not after drop
  const indicatorHeight =
    showIndicator && draggedCardHeight && isAnyDragging ? draggedCardHeight : 0;

  // Container style - collapse entire container when this card is being dragged
  // Note: margin-bottom is handled by CSS class for animation
  const containerStyle: React.CSSProperties = isDragging
    ? {
        height: 0,
        minHeight: 0,
        overflow: "hidden",
        padding: 0,
      }
    : {};

  return (
    <div
      className={`sortable-card-container ${isDragging ? "is-dragging" : ""} ${isAnyDragging ? "drag-active" : ""}`}
      style={containerStyle}
    >
      <div
        className={`drop-indicator ${isAnyDragging ? "dragging" : ""}`}
        style={{
          height: `${indicatorHeight}px`,
          marginBottom: indicatorHeight > 0 ? "8px" : "0px",
        }}
      />
      <div
        ref={setNodeRef}
        style={style}
        className="draggable-card-wrapper"
        data-story-id={story.id}
        {...attributes}
        {...listeners}
      >
        <StoryCard story={story} />
      </div>
      <style jsx>{`
        .sortable-card-container {
          position: relative;
          margin-bottom: 8px;
        }

        .sortable-card-container:last-child {
          margin-bottom: 0;
        }

        /* Smooth collapse animation when dragging this card out */
        .sortable-card-container.drag-active.is-dragging {
          margin-bottom: 0;
          transition:
            height 200ms ease,
            margin-bottom 200ms ease;
        }

        .drop-indicator {
          background: var(--bg-primary);
          border-radius: 12px;
          box-sizing: border-box;
        }

        :global([data-theme="light"]) .drop-indicator {
          background: #c0cac9;
        }

        .drop-indicator.dragging {
          transition:
            height 200ms ease,
            margin-bottom 200ms ease;
        }

        .draggable-card-wrapper {
          outline: none;
          border-radius: var(--radius-md);
        }

        .draggable-card-wrapper:focus-visible {
          outline: 2px solid var(--accent-blue);
          outline-offset: 2px;
        }
      `}</style>
    </div>
  );
}

export function DroppableColumn({ status, stories }: DroppableColumnProps) {
  const config = STATUS_CONFIG[status];
  const { draggedCardHeight, isDragging, overColumn, overStoryId } =
    useDragContext();

  // Show bottom indicator only when over column but not over any specific card
  const isColumnActive = overColumn === status;
  const showBottomIndicator = isColumnActive && !overStoryId;

  const { setNodeRef } = useDroppable({
    id: createDroppableId(status),
    data: {
      type: "column",
      status,
      storyCount: stories.length,
    } as DroppableData,
  });

  const sortableIds = stories.map((story) => createDraggableId(story.id));

  return (
    <div className="kanban-column">
      <div className="column-header">
        <h2 className="column-title">{config.label}</h2>
        <span className="story-count">{stories.length}</span>
      </div>

      <SortableContext
        items={sortableIds}
        strategy={verticalListSortingStrategy}
      >
        <div ref={setNodeRef} className="column-content">
          {stories.map((story, index) => (
            <SortableStoryCard
              key={story.id}
              story={story}
              sourceColumn={status}
              index={index}
            />
          ))}
          {/* Bottom drop zone - always render during drag for fade animation */}
          {stories.length > 0 && isDragging && (
            <div
              className={`drop-indicator-bottom ${showBottomIndicator ? "visible" : ""}`}
              style={{
                height: draggedCardHeight ? `${draggedCardHeight}px` : 60,
              }}
            />
          )}
          {stories.length === 0 && isDragging && (
            <div className="empty-drop-zone">
              <div
                className={`drop-indicator-empty ${showBottomIndicator ? "visible" : ""}`}
                style={{
                  height: draggedCardHeight ? `${draggedCardHeight}px` : 60,
                }}
              />
            </div>
          )}
        </div>
      </SortableContext>

      <style jsx>{`
        .kanban-column {
          display: flex;
          flex-direction: column;
          flex-shrink: 0;
          min-width: 300px;
          max-width: 300px;
          background: var(--bg-void);
          border: none;
          box-shadow: none;
          border-radius: var(--radius-lg);
        }

        .column-header {
          display: flex;
          align-items: center;
          gap: 10px;
          padding: 14px 16px;
          position: sticky;
          top: 0;
          background: var(--bg-void);
          z-index: 1;
          border-radius: var(--radius-lg) var(--radius-lg) 0 0;
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
          overflow-y: auto;
          min-height: 200px;
        }

        .empty-drop-zone {
          flex: 1;
          display: flex;
          align-items: flex-start;
        }

        .empty-placeholder {
          flex: 1;
          min-height: 60px;
        }

        .drop-indicator-empty {
          width: 100%;
          background: var(--bg-primary);
          border-radius: 12px;
          box-sizing: border-box;
          opacity: 0;
          transition: opacity 150ms ease-out;
        }

        .drop-indicator-empty.visible {
          opacity: 1;
          transition: opacity 80ms ease-in;
        }

        :global([data-theme="light"]) .drop-indicator-empty {
          background: #c0cac9;
        }

        .drop-indicator-bottom {
          background: var(--bg-primary);
          border-radius: 12px;
          box-sizing: border-box;
          flex-shrink: 0;
          opacity: 0;
          transition: opacity 150ms ease-out;
        }

        .drop-indicator-bottom.visible {
          opacity: 1;
          transition: opacity 80ms ease-in;
        }

        :global([data-theme="light"]) .drop-indicator-bottom {
          background: #c0cac9;
        }
      `}</style>
    </div>
  );
}
