/**
 * Tests for ImplementationContext component
 *
 * Per Issue #56:
 * - UI test: with code_context shows file list
 * - UI test: without code_context shows pending state
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ImplementationContext } from "../ImplementationContext";
import type { CodeContext } from "@/lib/types";

// Mock navigator.clipboard
const mockWriteText = jest.fn();
Object.assign(navigator, {
  clipboard: {
    writeText: mockWriteText,
  },
});

// Factory for creating mock code context
function createMockCodeContext(
  overrides: Partial<CodeContext> = {},
): CodeContext {
  return {
    classification: {
      category: "API",
      confidence: "high",
      reasoning: "Issue mentions API endpoints and REST patterns",
      keywords_matched: ["api", "endpoint", "rest"],
    },
    relevant_files: [
      {
        path: "src/api/routers/stories.py",
        line_start: 100,
        line_end: 150,
        relevance: "Main story API endpoints",
      },
      {
        path: "src/story_tracking/services/story_service.py",
        line_start: null,
        line_end: null,
        relevance: "Story service layer",
      },
    ],
    code_snippets: [
      {
        file_path: "src/api/routers/stories.py",
        line_start: 100,
        line_end: 110,
        content: 'def get_story(story_id: UUID):\n    """Get story by ID"""',
        language: "python",
        context: "Story retrieval endpoint",
      },
    ],
    exploration_duration_ms: 1500,
    classification_duration_ms: 200,
    explored_at: "2024-01-15T10:30:00Z",
    success: true,
    error: null,
    ...overrides,
  };
}

describe("ImplementationContext", () => {
  beforeEach(() => {
    mockWriteText.mockClear();
  });

  describe("pending state", () => {
    it("shows pending state when code_context is null", () => {
      render(<ImplementationContext codeContext={null} />);

      expect(screen.getByText("Implementation Context")).toBeInTheDocument();
      expect(
        screen.getByText("Implementation context pending"),
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Code area pointers will appear here/),
      ).toBeInTheDocument();
    });

    it("shows pending state when code_context has no files or snippets", () => {
      const emptyContext = createMockCodeContext({
        relevant_files: [],
        code_snippets: [],
      });

      render(<ImplementationContext codeContext={emptyContext} />);

      expect(
        screen.getByText("Implementation context pending"),
      ).toBeInTheDocument();
    });

    it("shows pending state when code_context success is false", () => {
      const failedContext = createMockCodeContext({
        success: false,
        error: "Failed to explore codebase",
      });

      render(<ImplementationContext codeContext={failedContext} />);

      expect(
        screen.getByText("Implementation context pending"),
      ).toBeInTheDocument();
    });
  });

  describe("with code context", () => {
    it("shows file list when code_context has files", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("Implementation Context")).toBeInTheDocument();
      expect(screen.getByText("Relevant Files")).toBeInTheDocument();
      expect(
        screen.getByText("src/api/routers/stories.py"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("src/story_tracking/services/story_service.py"),
      ).toBeInTheDocument();
    });

    it("shows classification info", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("Category:")).toBeInTheDocument();
      expect(screen.getByText("API")).toBeInTheDocument();
      expect(
        screen.getByText("Issue mentions API endpoints and REST patterns"),
      ).toBeInTheDocument();
    });

    it("shows confidence badge", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("high")).toBeInTheDocument();
    });

    it("shows matched keywords", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("api")).toBeInTheDocument();
      expect(screen.getByText("endpoint")).toBeInTheDocument();
      expect(screen.getByText("rest")).toBeInTheDocument();
    });

    it("shows code snippets when present", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("Code Snippets")).toBeInTheDocument();
      // Check for snippet content - use partial match since whitespace may vary
      expect(screen.getByText(/def get_story/)).toBeInTheDocument();
      expect(screen.getByText(/Get story by ID/)).toBeInTheDocument();
    });

    it("shows line numbers for files with ranges", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      // File with line range
      expect(screen.getByText(/:100-150/)).toBeInTheDocument();
    });

    it("shows file relevance descriptions", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("Main story API endpoints")).toBeInTheDocument();
      expect(screen.getByText("Story service layer")).toBeInTheDocument();
    });

    it("shows exploration timestamp", () => {
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText(/Explored Jan 15, 2024/)).toBeInTheDocument();
    });
  });

  describe("copy to clipboard", () => {
    it("copies file path when copy button is clicked", async () => {
      mockWriteText.mockResolvedValueOnce(undefined);
      const context = createMockCodeContext();

      render(<ImplementationContext codeContext={context} />);

      // Find and click the first copy button
      const copyButtons = screen.getAllByTitle("Copy path");
      fireEvent.click(copyButtons[0]);

      await waitFor(() => {
        expect(mockWriteText).toHaveBeenCalledWith(
          "src/api/routers/stories.py:100",
        );
      });
    });

    it("copies file path without line number when not present", async () => {
      mockWriteText.mockResolvedValueOnce(undefined);
      const context = createMockCodeContext({
        relevant_files: [
          {
            path: "src/config.py",
            line_start: null,
            line_end: null,
            relevance: "Config file",
          },
        ],
        code_snippets: [],
      });

      render(<ImplementationContext codeContext={context} />);

      const copyButtons = screen.getAllByTitle("Copy path");
      fireEvent.click(copyButtons[0]);

      await waitFor(() => {
        expect(mockWriteText).toHaveBeenCalledWith("src/config.py");
      });
    });
  });

  describe("without classification", () => {
    it("shows files without classification info", () => {
      const context = createMockCodeContext({
        classification: null,
      });

      render(<ImplementationContext codeContext={context} />);

      expect(screen.getByText("Relevant Files")).toBeInTheDocument();
      expect(screen.queryByText("Category:")).not.toBeInTheDocument();
    });
  });
});
