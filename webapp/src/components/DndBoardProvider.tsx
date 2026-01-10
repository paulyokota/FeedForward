"use client";

import {
  useState,
  useCallback,
  useRef,
  createContext,
  useContext,
} from "react";
import {
  DndContext,
  DragOverlay,
  pointerWithin,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
  type CollisionDetection,
  type DropAnimation,
} from "@dnd-kit/core";
import { sortableKeyboardCoordinates } from "@dnd-kit/sortable";
import { motion, AnimatePresence } from "framer-motion";
import type { Story, StatusKey } from "@/lib/types";
import { STATUS_CONFIG } from "@/lib/types";
import {
  type DraggableData,
  type DroppableData,
  type StoryMoveEvent,
  type ActiveDragState,
  extractStoryId,
} from "@/lib/dnd.types";
import { StoryCard } from "./StoryCard";

// Context for sharing drag state with children
interface DragContextValue {
  draggedCardHeight: number | null;
  isDragging: boolean;
  overColumn: StatusKey | null;
  overStoryId: string | null;
}

const DragContext = createContext<DragContextValue>({
  draggedCardHeight: null,
  isDragging: false,
  overColumn: null,
  overStoryId: null,
});

export function useDragContext() {
  return useContext(DragContext);
}

interface DndBoardProviderProps {
  children: React.ReactNode;
  onStoryMove: (event: StoryMoveEvent) => Promise<void>;
}

export function DndBoardProvider({
  children,
  onStoryMove,
}: DndBoardProviderProps) {
  const [activeDrag, setActiveDrag] = useState<ActiveDragState | null>(null);
  const [draggedCardHeight, setDraggedCardHeight] = useState<number | null>(
    null,
  );
  const [overColumn, setOverColumn] = useState<StatusKey | null>(null);
  const [overStoryId, setOverStoryId] = useState<string | null>(null);
  // Debounced version - delays clearing to prevent flicker during animation gaps
  const [stableOverStoryId, setStableOverStoryId] = useState<string | null>(
    null,
  );
  const storyIdTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const announcementRef = useRef<HTMLDivElement>(null);

  // Configure sensors with activation constraints
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // 8px movement before drag starts
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

  // Custom collision detection for kanban board
  // Uses ID patterns to distinguish: story-* for cards, column-* for columns
  const collisionDetection: CollisionDetection = useCallback((args) => {
    const pointerCollisions = pointerWithin(args);

    // Use ID pattern to identify collision types (more reliable than data path)
    const storyCollision = pointerCollisions.find((collision) =>
      String(collision.id).startsWith("story-"),
    );

    if (storyCollision) {
      // Pointer is within a story card - use it
      return [storyCollision];
    }

    // Check if pointer is within a column (but not over any story)
    const columnCollision = pointerCollisions.find((collision) =>
      String(collision.id).startsWith("column-"),
    );

    if (columnCollision) {
      // Over column area but not over any story (bottom or empty)
      return [columnCollision];
    }

    return pointerCollisions;
  }, []);

  // Announce to screen readers
  const announce = useCallback((message: string) => {
    if (announcementRef.current) {
      announcementRef.current.textContent = message;
    }
  }, []);

  const handleDragStart = useCallback(
    (event: DragStartEvent) => {
      const data = event.active.data.current as DraggableData | undefined;
      if (!data || data.type !== "story") return;

      // Measure the dragged element's height
      const element = document.querySelector(
        `[data-story-id="${data.story.id}"]`,
      );
      if (element) {
        setDraggedCardHeight(element.getBoundingClientRect().height);
      }

      setActiveDrag({
        id: event.active.id as `story-${string}`,
        story: data.story,
        sourceColumn: data.sourceColumn,
      });

      const columnLabel = STATUS_CONFIG[data.sourceColumn].label;
      announce(`Picked up ${data.story.title} from ${columnLabel}`);
    },
    [announce],
  );

  const handleDragOver = useCallback(
    (event: DragOverEvent) => {
      const overData = event.over?.data.current as
        | DroppableData
        | DraggableData
        | undefined;

      let newOverColumn: StatusKey | null = null;
      let newOverStoryId: string | null = null;

      if (overData?.type === "column") {
        newOverColumn = (overData as DroppableData).status;
      } else if (overData?.type === "story") {
        newOverColumn = (overData as DraggableData).sourceColumn;
        newOverStoryId = (overData as DraggableData).story.id;
      }

      if (newOverColumn !== overColumn) {
        setOverColumn(newOverColumn);
        if (newOverColumn && activeDrag) {
          const columnLabel = STATUS_CONFIG[newOverColumn].label;
          announce(`Over ${columnLabel}`);
        }
      }

      if (newOverStoryId !== overStoryId) {
        setOverStoryId(newOverStoryId);

        // Manage debounced stableOverStoryId to prevent flicker during animation gaps
        if (storyIdTimeoutRef.current) {
          clearTimeout(storyIdTimeoutRef.current);
          storyIdTimeoutRef.current = null;
        }

        if (newOverStoryId !== null) {
          // Immediately update when hovering over a story
          setStableOverStoryId(newOverStoryId);
        } else {
          // Delay clearing to handle animation gaps (200ms matches our animation)
          storyIdTimeoutRef.current = setTimeout(() => {
            setStableOverStoryId(null);
            storyIdTimeoutRef.current = null;
          }, 200);
        }
      }
    },
    [activeDrag, announce, overColumn, overStoryId],
  );

  const handleDragEnd = useCallback(
    async (event: DragEndEvent) => {
      const { active, over } = event;

      if (!activeDrag || !over) {
        // Clear any pending debounce timeout
        if (storyIdTimeoutRef.current) {
          clearTimeout(storyIdTimeoutRef.current);
          storyIdTimeoutRef.current = null;
        }
        setActiveDrag(null);
        setDraggedCardHeight(null);
        setOverColumn(null);
        setOverStoryId(null);
        setStableOverStoryId(null);
        announce("Drop cancelled");
        return;
      }

      const activeData = active.data.current as DraggableData;
      const overData = over.data.current as DroppableData | DraggableData;

      let targetStatus: StatusKey;
      let targetIndex: number;

      if (overData.type === "column") {
        targetStatus = (overData as DroppableData).status;
        targetIndex = (overData as DroppableData).storyCount;
      } else {
        targetStatus = (overData as DraggableData).sourceColumn;
        targetIndex = (overData as DraggableData).index;
      }

      const sourceStatus = activeData.sourceColumn;
      const sourceIndex = activeData.index;

      // Capture values we need for announcement before clearing state
      const storyTitle = activeDrag.story.title;
      const storyId = extractStoryId(activeDrag.id);

      // Clear any pending debounce timeout
      if (storyIdTimeoutRef.current) {
        clearTimeout(storyIdTimeoutRef.current);
        storyIdTimeoutRef.current = null;
      }

      // Clear drag state FIRST - before onStoryMove triggers re-render
      // This ensures indicators don't animate on drop
      setActiveDrag(null);
      setDraggedCardHeight(null);
      setOverColumn(null);
      setOverStoryId(null);
      setStableOverStoryId(null);

      if (sourceStatus !== targetStatus || sourceIndex !== targetIndex) {
        const moveEvent: StoryMoveEvent = {
          storyId,
          sourceStatus,
          targetStatus,
          sourceIndex,
          targetIndex,
        };

        try {
          await onStoryMove(moveEvent);
          const targetLabel = STATUS_CONFIG[targetStatus].label;
          announce(`Dropped ${storyTitle} in ${targetLabel}`);
        } catch (error) {
          announce("Move failed");
          console.error("Failed to move story:", error);
        }
      } else {
        announce("Returned to original position");
      }
    },
    [activeDrag, onStoryMove, announce],
  );

  const handleDragCancel = useCallback(() => {
    if (activeDrag) {
      announce(`Cancelled moving ${activeDrag.story.title}`);
    }
    // Clear any pending debounce timeout
    if (storyIdTimeoutRef.current) {
      clearTimeout(storyIdTimeoutRef.current);
      storyIdTimeoutRef.current = null;
    }
    setActiveDrag(null);
    setDraggedCardHeight(null);
    setOverColumn(null);
    setOverStoryId(null);
    setStableOverStoryId(null);
  }, [activeDrag, announce]);

  const dragContextValue: DragContextValue = {
    draggedCardHeight,
    isDragging: activeDrag !== null,
    overColumn,
    overStoryId: stableOverStoryId, // Use debounced version to prevent flicker
  };

  return (
    <DragContext.Provider value={dragContextValue}>
      <DndContext
        sensors={sensors}
        collisionDetection={collisionDetection}
        onDragStart={handleDragStart}
        onDragOver={handleDragOver}
        onDragEnd={handleDragEnd}
        onDragCancel={handleDragCancel}
      >
        {children}

        <AnimatePresence>
          {activeDrag && (
            <DragOverlay
              dropAnimation={{
                duration: 150,
                easing: "cubic-bezier(0.2, 0, 0, 1)",
              }}
            >
              <motion.div
                initial={{ scale: 1, rotate: 0 }}
                animate={{ scale: 1.02, rotate: 3 }}
                exit={{ scale: 1, rotate: 0 }}
                transition={{ duration: 0.2 }}
                className="drag-overlay-card"
              >
                <StoryCard story={activeDrag.story} isDragOverlay />
              </motion.div>
            </DragOverlay>
          )}
        </AnimatePresence>

        {/* ARIA live region for screen reader announcements */}
        <div
          ref={announcementRef}
          role="status"
          aria-live="assertive"
          aria-atomic="true"
          className="sr-only"
        />

        <style jsx global>{`
          .drag-overlay-card {
            cursor: grabbing;
            transform: rotate(3deg) scale(1.02);
            transition: transform 0.15s ease;
          }

          .drag-overlay-card :global(.story-card) {
            box-shadow:
              0 12px 28px rgba(0, 0, 0, 0.25),
              0 4px 10px rgba(0, 0, 0, 0.15);
          }

          .sr-only {
            position: absolute;
            width: 1px;
            height: 1px;
            padding: 0;
            margin: -1px;
            overflow: hidden;
            clip: rect(0, 0, 0, 0);
            white-space: nowrap;
            border: 0;
          }
        `}</style>
      </DndContext>
    </DragContext.Provider>
  );
}
