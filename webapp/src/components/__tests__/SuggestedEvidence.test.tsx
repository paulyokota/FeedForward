import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SuggestedEvidence } from "../SuggestedEvidence";
import { api } from "@/lib/api";

// Mock the API module
jest.mock("@/lib/api", () => ({
  api: {
    research: {
      getSuggestedEvidence: jest.fn(),
      acceptEvidence: jest.fn(),
      rejectEvidence: jest.fn(),
    },
  },
}));

const mockApi = api as jest.Mocked<typeof api>;

describe("SuggestedEvidence", () => {
  const storyId = "test-story-123";

  const mockSuggestions = [
    {
      id: "coda_page:page_1",
      source_type: "coda_page" as const,
      source_id: "page_1",
      title: "Research Page 1",
      snippet: "This is relevant research content...",
      similarity: 0.85,
      url: "https://coda.io/page_1",
      metadata: {},
      status: "suggested" as const,
    },
    {
      id: "coda_theme:theme_1",
      source_type: "coda_theme" as const,
      source_id: "theme_1",
      title: "Theme Research",
      snippet: "Theme-related content...",
      similarity: 0.75,
      url: "https://coda.io/theme_1",
      metadata: {},
      status: "accepted" as const,
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("Loading State", () => {
    it("shows loading indicator while fetching", () => {
      mockApi.research.getSuggestedEvidence.mockImplementation(
        () => new Promise(() => {}), // Never resolves
      );

      render(<SuggestedEvidence storyId={storyId} />);

      expect(
        screen.getByText("Finding related research..."),
      ).toBeInTheDocument();
    });
  });

  describe("Empty State", () => {
    it("renders nothing when no suggestions", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([]);

      const { container } = render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(container.firstChild).toBeNull();
      });
    });
  });

  describe("Suggestions Display", () => {
    it("renders suggested evidence cards", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue(mockSuggestions);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("Research Page 1")).toBeInTheDocument();
        expect(screen.getByText("Theme Research")).toBeInTheDocument();
      });
    });

    it("displays similarity scores as percentages", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue(mockSuggestions);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("85% match")).toBeInTheDocument();
        expect(screen.getByText("75% match")).toBeInTheDocument();
      });
    });

    it("shows source type badges", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue(mockSuggestions);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("Coda Research")).toBeInTheDocument();
        expect(screen.getByText("Coda Theme")).toBeInTheDocument();
      });
    });

    it("displays suggestion count", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue(mockSuggestions);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("2")).toBeInTheDocument();
      });
    });
  });

  describe("Status Display", () => {
    it("shows Accepted badge for accepted items", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        { ...mockSuggestions[1], status: "accepted" as const },
      ]);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("Accepted")).toBeInTheDocument();
      });
    });

    it("does not show Accepted badge for suggested items", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        { ...mockSuggestions[0], status: "suggested" as const },
      ]);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("Research Page 1")).toBeInTheDocument();
      });

      expect(screen.queryByText("Accepted")).not.toBeInTheDocument();
    });
  });

  describe("Action Buttons", () => {
    it("shows Accept and Reject buttons for suggested items", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /accept/i }),
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /reject/i }),
        ).toBeInTheDocument();
      });
    });

    it("shows Undo button for accepted items instead of Accept/Reject", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[1],
      ]);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /undo/i }),
        ).toBeInTheDocument();
      });

      // Accept button should not exist (not "Accept this evidence" aria-label)
      expect(
        screen.queryByRole("button", { name: /^accept this evidence$/i }),
      ).not.toBeInTheDocument();
      // Reject button should not exist
      expect(
        screen.queryByRole("button", { name: /^reject this evidence$/i }),
      ).not.toBeInTheDocument();
    });

    it("shows View link for all items", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue(mockSuggestions);

      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        const viewLinks = screen.getAllByRole("link", { name: /view/i });
        expect(viewLinks).toHaveLength(2);
        expect(viewLinks[0]).toHaveAttribute("href", "https://coda.io/page_1");
        expect(viewLinks[1]).toHaveAttribute("href", "https://coda.io/theme_1");
      });
    });
  });

  describe("Accept Action", () => {
    it("calls accept API when clicking Accept button", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.acceptEvidence.mockResolvedValue({ success: true });

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /accept/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /accept/i }));

      expect(mockApi.research.acceptEvidence).toHaveBeenCalledWith(
        storyId,
        "coda_page:page_1",
      );
    });

    it("updates item to accepted status after successful accept", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.acceptEvidence.mockResolvedValue({ success: true });

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /accept/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /accept/i }));

      await waitFor(() => {
        expect(screen.getByText("Accepted")).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /undo/i }),
        ).toBeInTheDocument();
      });
    });

    it("calls onEvidenceAccepted callback when provided", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.acceptEvidence.mockResolvedValue({ success: true });

      const onAccepted = jest.fn();
      const user = userEvent.setup();
      render(
        <SuggestedEvidence storyId={storyId} onEvidenceAccepted={onAccepted} />,
      );

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /accept/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /accept/i }));

      await waitFor(() => {
        expect(onAccepted).toHaveBeenCalled();
      });
    });
  });

  describe("Reject Action", () => {
    it("calls reject API when clicking Reject button", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.rejectEvidence.mockResolvedValue({ success: true });

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /reject/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /reject/i }));

      expect(mockApi.research.rejectEvidence).toHaveBeenCalledWith(
        storyId,
        "coda_page:page_1",
      );
    });

    it("removes item from UI after successful reject", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.rejectEvidence.mockResolvedValue({ success: true });

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("Research Page 1")).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /reject/i }));

      await waitFor(() => {
        expect(screen.queryByText("Research Page 1")).not.toBeInTheDocument();
      });
    });
  });

  describe("Undo Action (State Transition)", () => {
    it("calls reject API when clicking Undo button on accepted item", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[1],
      ]);
      mockApi.research.rejectEvidence.mockResolvedValue({ success: true });

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /undo/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /undo/i }));

      expect(mockApi.research.rejectEvidence).toHaveBeenCalledWith(
        storyId,
        "coda_theme:theme_1",
      );
    });

    it("removes accepted item from UI after undo", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[1],
      ]);
      mockApi.research.rejectEvidence.mockResolvedValue({ success: true });

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByText("Theme Research")).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /undo/i }));

      await waitFor(() => {
        expect(screen.queryByText("Theme Research")).not.toBeInTheDocument();
      });
    });
  });

  describe("Processing State", () => {
    it("disables buttons during processing", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.acceptEvidence.mockImplementation(
        () => new Promise(() => {}), // Never resolves
      );

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /accept/i })).toBeEnabled();
      });

      await user.click(screen.getByRole("button", { name: /accept/i }));

      expect(screen.getByRole("button", { name: /accept/i })).toBeDisabled();
      expect(screen.getByRole("button", { name: /reject/i })).toBeDisabled();
    });
  });

  describe("Error Handling", () => {
    it("handles API fetch error gracefully", async () => {
      mockApi.research.getSuggestedEvidence.mockRejectedValue(
        new Error("API Error"),
      );

      const { container } = render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        // Should render nothing on error (silent failure)
        expect(container.firstChild).toBeNull();
      });
    });

    it("handles accept error gracefully without crashing", async () => {
      mockApi.research.getSuggestedEvidence.mockResolvedValue([
        mockSuggestions[0],
      ]);
      mockApi.research.acceptEvidence.mockRejectedValue(
        new Error("Accept failed"),
      );

      const user = userEvent.setup();
      render(<SuggestedEvidence storyId={storyId} />);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /accept/i }),
        ).toBeInTheDocument();
      });

      await user.click(screen.getByRole("button", { name: /accept/i }));

      // Should still show the item (not updated)
      await waitFor(() => {
        expect(screen.getByText("Research Page 1")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /accept/i })).toBeEnabled();
      });
    });
  });
});
