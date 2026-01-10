/**
 * Drag-and-Drop Types for Kanban Board
 *
 * Types for implementing kanban drag-and-drop using dnd-kit.
 */

import type { Story, StatusKey } from "./types";

/** Unique identifier format for draggable items */
export type DraggableId = `story-${string}`;

/** Unique identifier format for droppable columns */
export type DroppableId = `column-${StatusKey}`;

/** Data attached to draggable items */
export interface DraggableData {
  type: "story";
  story: Story;
  sourceColumn: StatusKey;
  index: number;
}

/** Data attached to droppable columns */
export interface DroppableData {
  type: "column";
  status: StatusKey;
  storyCount: number;
}

/** Event fired when a drag operation completes */
export interface StoryMoveEvent {
  storyId: string;
  sourceStatus: StatusKey;
  targetStatus: StatusKey;
  sourceIndex: number;
  targetIndex: number;
}

/** Active drag state for overlay rendering */
export interface ActiveDragState {
  id: DraggableId;
  story: Story;
  sourceColumn: StatusKey;
}

/** Props for DndBoardProvider */
export interface DndBoardProviderProps {
  children: React.ReactNode;
  onStoryMove: (event: StoryMoveEvent) => Promise<void>;
}

/** Props for DroppableColumn */
export interface DroppableColumnProps {
  status: StatusKey;
  stories: Story[];
  isOver?: boolean;
}

/** Props for DraggableStoryCard */
export interface DraggableStoryCardProps {
  story: Story;
  sourceColumn: StatusKey;
  index: number;
  isDragging?: boolean;
}

/** Keyboard navigation announcements */
export interface DndAnnouncements {
  onDragStart: (id: string) => string;
  onDragOver: (id: string, overId: string) => string;
  onDragEnd: (id: string, overId: string | null) => string;
  onDragCancel: (id: string) => string;
}

/** Helper to create draggable ID */
export function createDraggableId(storyId: string): DraggableId {
  return `story-${storyId}`;
}

/** Helper to create droppable ID */
export function createDroppableId(status: StatusKey): DroppableId {
  return `column-${status}`;
}

/** Extract story ID from draggable ID */
export function extractStoryId(draggableId: DraggableId): string {
  return draggableId.replace("story-", "");
}

/** Extract status from droppable ID */
export function extractStatus(droppableId: DroppableId): StatusKey {
  return droppableId.replace("column-", "") as StatusKey;
}
