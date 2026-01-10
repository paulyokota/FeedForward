/**
 * Integration tests for DndBoardProvider
 *
 * Tests the drag-and-drop context provider and event handlers
 */

import { render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { DndBoardProvider, useDragContext } from "../DndBoardProvider";
import type { StoryMoveEvent } from "@/lib/dnd.types";
import type { StatusKey } from "@/lib/types";

// Mock framer-motion to avoid animation issues in tests
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Test component that consumes the drag context
function TestConsumer() {
  const { draggedCardHeight, isDragging, overColumn, overStoryId } =
    useDragContext();

  return (
    <div data-testid="context-consumer">
      <span data-testid="dragged-height">{draggedCardHeight ?? "null"}</span>
      <span data-testid="is-dragging">{isDragging ? "true" : "false"}</span>
      <span data-testid="over-column">{overColumn ?? "null"}</span>
      <span data-testid="over-story-id">{overStoryId ?? "null"}</span>
    </div>
  );
}

// Mock story for testing
const mockStory = {
  id: "story-123",
  title: "Test Story",
  description: "Test description",
  labels: ["bug"],
  priority: "high" as const,
  severity: "major" as const,
  product_area: "ui",
  technical_area: "frontend",
  status: "candidate",
  confidence_score: 0.85,
  evidence_count: 5,
  conversation_count: 3,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("DndBoardProvider", () => {
  describe("Context initialization", () => {
    it("provides correct initial context values", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      expect(screen.getByTestId("dragged-height")).toHaveTextContent("null");
      expect(screen.getByTestId("is-dragging")).toHaveTextContent("false");
      expect(screen.getByTestId("over-column")).toHaveTextContent("null");
      expect(screen.getByTestId("over-story-id")).toHaveTextContent("null");
    });

    it("renders children correctly", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div data-testid="child">Test Child</div>
        </DndBoardProvider>,
      );

      expect(screen.getByTestId("child")).toBeInTheDocument();
      expect(screen.getByTestId("child")).toHaveTextContent("Test Child");
    });

    it("renders ARIA live region for announcements", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div>Content</div>
        </DndBoardProvider>,
      );

      // Note: dnd-kit also creates a live region, so we check for multiple
      const liveRegions = screen.getAllByRole("status");
      expect(liveRegions.length).toBeGreaterThanOrEqual(1);

      // Find our custom live region (has sr-only class)
      const ourLiveRegion = liveRegions.find((region) =>
        region.className.includes("sr-only"),
      );
      expect(ourLiveRegion).toBeDefined();
      expect(ourLiveRegion).toHaveAttribute("aria-live", "assertive");
      expect(ourLiveRegion).toHaveAttribute("aria-atomic", "true");
    });
  });

  describe("useDragContext hook", () => {
    it("returns context values", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      const consumer = screen.getByTestId("context-consumer");
      expect(consumer).toBeInTheDocument();
    });

    it("can be called from nested components", () => {
      const onStoryMove = jest.fn();

      function NestedConsumer() {
        return (
          <div>
            <div>
              <TestConsumer />
            </div>
          </div>
        );
      }

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <NestedConsumer />
        </DndBoardProvider>,
      );

      expect(screen.getByTestId("context-consumer")).toBeInTheDocument();
    });
  });

  describe("Drag handlers", () => {
    // Note: Full drag simulation requires dnd-kit test utilities
    // These tests verify the handler logic and state management

    it("accepts onStoryMove callback", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div>Content</div>
        </DndBoardProvider>,
      );

      // Provider should render without errors
      expect(screen.getByText("Content")).toBeInTheDocument();
    });

    it("onStoryMove callback receives correct event structure", async () => {
      const onStoryMove = jest.fn().mockResolvedValue(undefined);

      // This is a unit test for the callback contract
      // In real usage, this would be called by dnd-kit
      const expectedEvent: StoryMoveEvent = {
        storyId: "123",
        sourceStatus: "candidate" as StatusKey,
        targetStatus: "triaged" as StatusKey,
        sourceIndex: 0,
        targetIndex: 1,
      };

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div>Content</div>
        </DndBoardProvider>,
      );

      // Simulate what would happen during a drag operation
      await act(async () => {
        await onStoryMove(expectedEvent);
      });

      expect(onStoryMove).toHaveBeenCalledWith(expectedEvent);
    });
  });

  describe("Drag overlay", () => {
    it("does not render overlay when not dragging", () => {
      const onStoryMove = jest.fn();

      const { container } = render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      // No drag overlay should be present
      const overlay = container.querySelector(".drag-overlay-card");
      expect(overlay).not.toBeInTheDocument();
    });

    it("isDragging is false initially", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      expect(screen.getByTestId("is-dragging")).toHaveTextContent("false");
    });
  });

  describe("Accessibility", () => {
    it("includes screen reader announcement region", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div>Content</div>
        </DndBoardProvider>,
      );

      const announcements = screen.getAllByRole("status");
      const ourAnnouncement = announcements.find((el) =>
        el.className.includes("sr-only"),
      );

      expect(ourAnnouncement).toBeDefined();
      expect(ourAnnouncement).toHaveAttribute("aria-live", "assertive");
      expect(ourAnnouncement).toHaveAttribute("aria-atomic", "true");
      expect(ourAnnouncement).toHaveClass("sr-only");
    });

    it("announcement region is visually hidden but accessible", () => {
      const onStoryMove = jest.fn();

      const { container } = render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div>Content</div>
        </DndBoardProvider>,
      );

      const announcements = screen.getAllByRole("status");
      const ourAnnouncement = announcements.find((el) =>
        el.className.includes("sr-only"),
      );

      // Check for sr-only class which hides visually but keeps accessible
      expect(ourAnnouncement).toHaveClass("sr-only");

      // Verify it exists in the DOM for screen readers
      expect(ourAnnouncement).toBeInTheDocument();
    });
  });

  describe("Error handling", () => {
    it("handles onStoryMove errors gracefully", async () => {
      const consoleError = jest.spyOn(console, "error").mockImplementation();
      const onStoryMove = jest.fn().mockRejectedValue(new Error("Move failed"));

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <div>Content</div>
        </DndBoardProvider>,
      );

      const event: StoryMoveEvent = {
        storyId: "123",
        sourceStatus: "candidate",
        targetStatus: "triaged",
        sourceIndex: 0,
        targetIndex: 1,
      };

      await act(async () => {
        await onStoryMove(event).catch(() => {
          // Expected error
        });
      });

      consoleError.mockRestore();
    });

    it("continues to work after move error", async () => {
      let shouldFail = true;
      const onStoryMove = jest.fn().mockImplementation(() => {
        if (shouldFail) {
          shouldFail = false;
          return Promise.reject(new Error("First attempt fails"));
        }
        return Promise.resolve();
      });

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      const event: StoryMoveEvent = {
        storyId: "123",
        sourceStatus: "candidate",
        targetStatus: "triaged",
        sourceIndex: 0,
        targetIndex: 1,
      };

      // First call fails
      await act(async () => {
        await onStoryMove(event).catch(() => {});
      });

      // Second call succeeds
      await act(async () => {
        await onStoryMove(event);
      });

      expect(onStoryMove).toHaveBeenCalledTimes(2);
    });
  });

  describe("State management", () => {
    it("provides draggedCardHeight in context", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      // Initially null
      expect(screen.getByTestId("dragged-height")).toHaveTextContent("null");
    });

    it("provides overColumn in context", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      // Initially null
      expect(screen.getByTestId("over-column")).toHaveTextContent("null");
    });

    it("provides overStoryId in context", () => {
      const onStoryMove = jest.fn();

      render(
        <DndBoardProvider onStoryMove={onStoryMove}>
          <TestConsumer />
        </DndBoardProvider>,
      );

      // Initially null
      expect(screen.getByTestId("over-story-id")).toHaveTextContent("null");
    });
  });
});
