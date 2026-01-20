/**
 * Pipeline Page Tests
 *
 * Tests for the Pipeline control page including the New Stories panel (Issue #54).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import PipelinePage from "../page";
import { api } from "@/lib/api";

// Mock the API client
jest.mock("@/lib/api", () => ({
  api: {
    pipeline: {
      active: jest.fn(),
      history: jest.fn(),
      status: jest.fn(),
      run: jest.fn(),
      stop: jest.fn(),
    },
    stories: {
      list: jest.fn(),
    },
  },
}));

// Mock next/link
jest.mock("next/link", () => {
  return function MockLink({
    children,
    href,
  }: {
    children: React.ReactNode;
    href: string;
  }) {
    return <a href={href}>{children}</a>;
  };
});

// Mock the theme-dependent components
jest.mock("@/components/ThemeToggle", () => ({
  ThemeToggle: () => <div data-testid="theme-toggle">Theme Toggle</div>,
}));

jest.mock("@/components/FeedForwardLogo", () => ({
  FeedForwardLogo: () => <div data-testid="logo">FeedForward</div>,
}));

const mockPipelineHistory = [
  {
    id: 1,
    started_at: "2025-01-20T10:00:00Z",
    completed_at: "2025-01-20T10:15:00Z",
    status: "completed",
    conversations_fetched: 100,
    conversations_classified: 95,
    conversations_stored: 90,
    duration_seconds: 900,
  },
  {
    id: 2,
    started_at: "2025-01-19T10:00:00Z",
    completed_at: "2025-01-19T10:10:00Z",
    status: "completed",
    conversations_fetched: 50,
    conversations_classified: 48,
    conversations_stored: 45,
    duration_seconds: 600,
  },
];

const mockNewStories = [
  {
    id: "story-uuid-1",
    title: "Users report scheduling issues",
    description: "Multiple users reporting that scheduled pins fail to post",
    labels: ["bug", "scheduler"],
    priority: "high",
    severity: "major",
    product_area: "Scheduler",
    technical_area: "Backend",
    status: "candidate",
    confidence_score: 85.5,
    evidence_count: 3,
    conversation_count: 5,
    created_at: "2025-01-20T10:05:00Z",
    updated_at: "2025-01-20T10:05:00Z",
  },
  {
    id: "story-uuid-2",
    title: "Analytics dashboard loading slowly",
    description: "Dashboard takes too long to load with large datasets",
    labels: ["performance"],
    priority: "medium",
    severity: "moderate",
    product_area: "Analytics",
    technical_area: "Frontend",
    status: "candidate",
    confidence_score: 72.0,
    evidence_count: 2,
    conversation_count: 3,
    created_at: "2025-01-20T10:08:00Z",
    updated_at: "2025-01-20T10:08:00Z",
  },
];

describe("PipelinePage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (api.pipeline.active as jest.Mock).mockResolvedValue({
      active: false,
      run_id: null,
    });
    (api.pipeline.history as jest.Mock).mockResolvedValue(mockPipelineHistory);
    (api.stories.list as jest.Mock).mockResolvedValue({
      stories: mockNewStories,
      total: 2,
      limit: 50,
      offset: 0,
    });
  });

  describe("New Stories Panel", () => {
    it("shows new stories count in the panel header", async () => {
      render(<PipelinePage />);

      await waitFor(() => {
        expect(screen.getByText("New Stories Created")).toBeInTheDocument();
      });

      expect(screen.getByText("(2)")).toBeInTheDocument();
    });

    it("renders story cards with title and status", async () => {
      render(<PipelinePage />);

      await waitFor(() => {
        expect(
          screen.getByText("Users report scheduling issues"),
        ).toBeInTheDocument();
      });

      expect(
        screen.getByText("Analytics dashboard loading slowly"),
      ).toBeInTheDocument();
      expect(screen.getAllByText("candidate")).toHaveLength(2);
    });

    it("renders story description truncated if too long", async () => {
      const longDescription =
        "This is a very long description that exceeds 120 characters. It should be truncated with an ellipsis to fit in the card preview area properly.";
      (api.stories.list as jest.Mock).mockResolvedValue({
        stories: [
          {
            ...mockNewStories[0],
            description: longDescription,
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      });

      render(<PipelinePage />);

      await waitFor(() => {
        expect(screen.getByText(/This is a very long/)).toBeInTheDocument();
      });

      // Check that description is truncated
      const descriptionElement = screen.getByText(/This is a very long/);
      expect(descriptionElement.textContent).toContain("...");
      expect(descriptionElement.textContent?.length).toBeLessThanOrEqual(124); // 120 + "..."
    });

    it("shows product area badge on story cards", async () => {
      render(<PipelinePage />);

      await waitFor(() => {
        expect(screen.getByText("Scheduler")).toBeInTheDocument();
      });

      // Use getAllByText since "Analytics" appears in both nav and story card
      const analyticsElements = screen.getAllByText("Analytics");
      // At least one should be in the story card (with class story-area)
      expect(
        analyticsElements.some(
          (el) =>
            el.classList.contains("story-area") ||
            el.parentElement?.classList.contains("story-meta"),
        ),
      ).toBe(true);
    });

    it("links to story detail page", async () => {
      render(<PipelinePage />);

      await waitFor(() => {
        expect(
          screen.getByText("Users report scheduling issues"),
        ).toBeInTheDocument();
      });

      const links = screen.getAllByRole("link");
      const storyLink = links.find(
        (link) => link.getAttribute("href") === "/story/story-uuid-1",
      );
      expect(storyLink).toBeInTheDocument();
    });

    it("shows empty state when no new stories", async () => {
      (api.stories.list as jest.Mock).mockResolvedValue({
        stories: [],
        total: 0,
        limit: 50,
        offset: 0,
      });

      render(<PipelinePage />);

      await waitFor(() => {
        expect(
          screen.getByText("No new stories from this run"),
        ).toBeInTheDocument();
      });
    });

    it("fetches stories with created_since from run start time", async () => {
      render(<PipelinePage />);

      await waitFor(() => {
        expect(api.stories.list).toHaveBeenCalledWith({
          created_since: "2025-01-20T10:00:00Z",
          limit: 50,
        });
      });
    });
  });

  describe("Run History", () => {
    it("shows hint text about clicking completed runs", async () => {
      render(<PipelinePage />);

      await waitFor(() => {
        expect(
          screen.getByText(
            "Click a completed run to see stories created during that run",
          ),
        ).toBeInTheDocument();
      });
    });

    it("fetches new stories when clicking a different completed run", async () => {
      const user = userEvent.setup();
      render(<PipelinePage />);

      await waitFor(() => {
        expect(screen.getByText("#1")).toBeInTheDocument();
      });

      // Click on the second run
      const runRows = screen.getAllByRole("button");
      const secondRunRow = runRows.find((row) =>
        row.textContent?.includes("#2"),
      );

      if (secondRunRow) {
        await user.click(secondRunRow);

        await waitFor(() => {
          expect(api.stories.list).toHaveBeenCalledWith({
            created_since: "2025-01-19T10:00:00Z",
            limit: 50,
          });
        });
      }
    });
  });
});
