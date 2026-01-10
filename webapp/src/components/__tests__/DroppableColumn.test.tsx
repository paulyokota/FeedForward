/**
 * Component tests for DroppableColumn
 *
 * Tests column rendering, drop zones, and sortable card behavior
 */

import { render, screen } from "@testing-library/react";
import { DroppableColumn } from "../DroppableColumn";
import type { Story, StatusKey } from "@/lib/types";

// Mock dnd-kit hooks
const mockUseSortable = jest.fn();
const mockUseDragContext = jest.fn();

jest.mock("@dnd-kit/core", () => ({
  ...jest.requireActual("@dnd-kit/core"),
  useDroppable: jest.fn(() => ({
    setNodeRef: jest.fn(),
    isOver: false,
  })),
}));

jest.mock("@dnd-kit/sortable", () => ({
  ...jest.requireActual("@dnd-kit/sortable"),
  SortableContext: ({ children }: any) => <div>{children}</div>,
  verticalListSortingStrategy: {},
  useSortable: () => mockUseSortable(),
}));

jest.mock("../DndBoardProvider", () => ({
  useDragContext: () => mockUseDragContext(),
}));

// Mock framer-motion
jest.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock StoryCard to simplify testing
jest.mock("../StoryCard", () => ({
  StoryCard: ({ story }: any) => (
    <div data-testid={`story-card-${story.id}`}>{story.title}</div>
  ),
}));

// Helper to create mock stories
function createMockStory(overrides: Partial<Story> = {}): Story {
  return {
    id: `story-${Math.random()}`,
    title: "Test Story",
    description: "Test description",
    labels: ["bug"],
    priority: "high",
    severity: "major",
    product_area: "ui",
    technical_area: "frontend",
    status: "candidate",
    confidence_score: 0.85,
    evidence_count: 5,
    conversation_count: 3,
    created_at: "2024-01-01T00:00:00Z",
    updated_at: "2024-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("DroppableColumn", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Reset to default mock implementations
    mockUseSortable.mockReturnValue({
      attributes: {},
      listeners: {},
      setNodeRef: jest.fn(),
      transform: null,
      isDragging: false,
      isOver: false,
    });
    mockUseDragContext.mockReturnValue({
      draggedCardHeight: null,
      isDragging: false,
      overColumn: null,
      overStoryId: null,
    });
  });

  describe("Column header", () => {
    it("renders status label correctly", () => {
      const stories: Story[] = [];

      render(<DroppableColumn status="candidate" stories={stories} />);

      expect(screen.getByText("Candidate")).toBeInTheDocument();
    });

    it.each<[StatusKey, string]>([
      ["candidate", "Candidate"],
      ["triaged", "Triaged"],
      ["in_progress", "In Progress"],
      ["done", "Done"],
      ["dismissed", "Dismissed"],
    ])('renders correct label for status "%s"', (status, expectedLabel) => {
      render(<DroppableColumn status={status} stories={[]} />);

      expect(screen.getByText(expectedLabel)).toBeInTheDocument();
    });

    it("displays correct story count with no stories", () => {
      render(<DroppableColumn status="candidate" stories={[]} />);

      expect(screen.getByText("0")).toBeInTheDocument();
    });

    it("displays correct story count with multiple stories", () => {
      const stories = [
        createMockStory({ id: "1" }),
        createMockStory({ id: "2" }),
        createMockStory({ id: "3" }),
      ];

      render(<DroppableColumn status="triaged" stories={stories} />);

      expect(screen.getByText("3")).toBeInTheDocument();
    });
  });

  describe("Story card rendering", () => {
    it("renders all story cards", () => {
      const stories = [
        createMockStory({ id: "1", title: "Story 1" }),
        createMockStory({ id: "2", title: "Story 2" }),
        createMockStory({ id: "3", title: "Story 3" }),
      ];

      render(<DroppableColumn status="candidate" stories={stories} />);

      expect(screen.getByText("Story 1")).toBeInTheDocument();
      expect(screen.getByText("Story 2")).toBeInTheDocument();
      expect(screen.getByText("Story 3")).toBeInTheDocument();
    });

    it("renders cards with sortable wrappers", () => {
      const stories = [createMockStory({ id: "story-123" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const wrapper = container.querySelector('[data-story-id="story-123"]');
      expect(wrapper).toBeInTheDocument();
      expect(wrapper).toHaveClass("draggable-card-wrapper");
    });

    it("renders empty column when no stories", () => {
      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      const content = container.querySelector(".column-content");
      expect(content).toBeInTheDocument();
      expect(content?.children.length).toBe(0);
    });

    it("maintains story order", () => {
      const stories = [
        createMockStory({ id: "1", title: "First" }),
        createMockStory({ id: "2", title: "Second" }),
        createMockStory({ id: "3", title: "Third" }),
      ];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const storyCards = container.querySelectorAll(
        '[data-testid^="story-card-"]',
      );
      expect(storyCards).toHaveLength(3);
      expect(storyCards[0]).toHaveTextContent("First");
      expect(storyCards[1]).toHaveTextContent("Second");
      expect(storyCards[2]).toHaveTextContent("Third");
    });
  });

  describe("Drop indicators", () => {
    it("shows drop indicator when dragging over a card", () => {
      mockUseSortable.mockReturnValue({
        attributes: {},
        listeners: {},
        setNodeRef: jest.fn(),
        transform: null,
        isDragging: false,
        isOver: true, // Card is being hovered
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const indicator = container.querySelector(".drop-indicator");
      expect(indicator).toBeInTheDocument();
    });

    it("does not show drop indicator when card not being dragged over", () => {
      mockUseSortable.mockReturnValue({
        attributes: {},
        listeners: {},
        setNodeRef: jest.fn(),
        transform: null,
        isDragging: false,
        isOver: false,
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const indicator = container.querySelector(".drop-indicator");
      // Indicator is rendered but with height 0 when not active
      expect(indicator).toHaveStyle({ height: "0px" });
    });

    it("does not show indicator on card being dragged", () => {
      mockUseSortable.mockReturnValue({
        attributes: {},
        listeners: {},
        setNodeRef: jest.fn(),
        transform: null,
        isDragging: true, // This card is being dragged
        isOver: true,
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const indicator = container.querySelector(".drop-indicator");
      // Indicator is rendered but with height 0 when card is being dragged
      expect(indicator).toHaveStyle({ height: "0px" });
    });

    it("uses draggedCardHeight for indicator sizing", () => {
      mockUseSortable.mockReturnValue({
        attributes: {},
        listeners: {},
        setNodeRef: jest.fn(),
        transform: null,
        isDragging: false,
        isOver: true,
      });

      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 120,
        isDragging: true,
        overColumn: "candidate" as StatusKey,
        overStoryId: null,
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const indicator = container.querySelector(".drop-indicator");
      expect(indicator).toHaveStyle({ height: "120px" });
    });
  });

  describe("Empty column drop zone", () => {
    it("shows empty drop zone when column is empty and dragging", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 100,
        isDragging: true,
        overColumn: "candidate" as StatusKey,
        overStoryId: null,
      });

      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      const emptyZone = container.querySelector(".empty-drop-zone");
      expect(emptyZone).toBeInTheDocument();
    });

    it("does not show empty drop zone when not dragging", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: null,
        isDragging: false,
        overColumn: null,
        overStoryId: null,
      });

      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      const emptyZone = container.querySelector(".empty-drop-zone");
      expect(emptyZone).not.toBeInTheDocument();
    });

    it("shows indicator in empty column when over it", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 100,
        isDragging: true,
        overColumn: "candidate" as StatusKey,
        overStoryId: null,
      });

      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      const indicator = container.querySelector(".drop-indicator-empty");
      expect(indicator).toBeInTheDocument();
      expect(indicator).toHaveStyle({ height: "100px" });
    });

    it("shows placeholder in empty column when not over it", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 100,
        isDragging: true,
        overColumn: "triaged" as StatusKey, // Different column
        overStoryId: null,
      });

      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      // Indicator is rendered for fade animation but not visible (no .visible class)
      const indicator = container.querySelector(".drop-indicator-empty");
      expect(indicator).toBeInTheDocument();
      expect(indicator).not.toHaveClass("visible");
    });
  });

  describe("Bottom drop indicator", () => {
    it("shows bottom indicator when over column but not over any card", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 120,
        isDragging: true,
        overColumn: "candidate" as StatusKey,
        overStoryId: null, // Not over any specific story
      });

      const stories = [
        createMockStory({ id: "1" }),
        createMockStory({ id: "2" }),
      ];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const bottomIndicator = container.querySelector(".drop-indicator-bottom");
      expect(bottomIndicator).toBeInTheDocument();
      expect(bottomIndicator).toHaveStyle({ height: "120px" });
    });

    it("does not show bottom indicator when over a specific card", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 120,
        isDragging: true,
        overColumn: "candidate" as StatusKey,
        overStoryId: "story-1", // Over a specific story
      });

      const stories = [
        createMockStory({ id: "story-1" }),
        createMockStory({ id: "story-2" }),
      ];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      // Indicator is rendered for fade animation but not visible (no .visible class)
      const bottomIndicator = container.querySelector(".drop-indicator-bottom");
      expect(bottomIndicator).toBeInTheDocument();
      expect(bottomIndicator).not.toHaveClass("visible");
    });

    it("does not show bottom indicator in different column", () => {
      mockUseDragContext.mockReturnValue({
        draggedCardHeight: 120,
        isDragging: true,
        overColumn: "triaged" as StatusKey, // Different column
        overStoryId: null,
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      // Indicator is rendered for fade animation but not visible (no .visible class)
      const bottomIndicator = container.querySelector(".drop-indicator-bottom");
      expect(bottomIndicator).toBeInTheDocument();
      expect(bottomIndicator).not.toHaveClass("visible");
    });
  });

  describe("Accessibility", () => {
    it("uses semantic HTML structure", () => {
      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      const heading = screen.getByRole("heading", { name: "Candidate" });
      expect(heading).toBeInTheDocument();
      expect(heading.tagName).toBe("H2");
    });

    it("draggable cards support keyboard interaction", () => {
      mockUseSortable.mockReturnValue({
        attributes: { role: "button", tabIndex: 0 },
        listeners: { onKeyDown: jest.fn() },
        setNodeRef: jest.fn(),
        transform: null,
        isDragging: false,
        isOver: false,
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const wrapper = container.querySelector(".draggable-card-wrapper");
      expect(wrapper).toHaveAttribute("role", "button");
      expect(wrapper).toHaveAttribute("tabIndex", "0");
    });
  });

  describe("Visual styling", () => {
    it("applies correct column structure", () => {
      const { container } = render(
        <DroppableColumn status="candidate" stories={[]} />,
      );

      const column = container.querySelector(".kanban-column");
      expect(column).toBeInTheDocument();

      const header = container.querySelector(".column-header");
      expect(header).toBeInTheDocument();

      const content = container.querySelector(".column-content");
      expect(content).toBeInTheDocument();
    });

    it("applies cursor styling to draggable cards", () => {
      mockUseSortable.mockReturnValue({
        attributes: {},
        listeners: {},
        setNodeRef: jest.fn(),
        transform: null,
        isDragging: false,
        isOver: false,
      });

      const stories = [createMockStory({ id: "1" })];

      const { container } = render(
        <DroppableColumn status="candidate" stories={stories} />,
      );

      const wrapper = container.querySelector(".draggable-card-wrapper");
      expect(wrapper).toHaveStyle({ cursor: "grab" });
    });
  });
});
