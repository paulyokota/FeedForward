/**
 * Minimal tests for EvidenceBrowser
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { EvidenceBrowser } from "../EvidenceBrowser";
import type { StoryEvidence } from "@/lib/types";

const mockEvidence: StoryEvidence = {
  id: "ev-123",
  story_id: "test-123",
  conversation_ids: ["conv-1"],
  theme_signatures: ["billing_issue"],
  source_stats: { intercom: 1 },
  excerpts: [
    {
      text: "I can't pay my bill",
      conversation_id: "conv-1",
      source: "intercom",
      timestamp: "2024-01-01T00:00:00Z",
    },
  ],
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
};

describe("EvidenceBrowser", () => {
  it("renders with evidence data", () => {
    render(<EvidenceBrowser evidence={mockEvidence} />);
    expect(screen.getByText(/I can't pay my bill/)).toBeInTheDocument();
  });

  it("renders empty state when no evidence", () => {
    render(<EvidenceBrowser evidence={null} />);
    expect(screen.getByText(/No evidence/i)).toBeInTheDocument();
  });

  it("renders empty state when no excerpts", () => {
    const emptyEvidence: StoryEvidence = {
      ...mockEvidence,
      excerpts: [],
    };
    render(<EvidenceBrowser evidence={emptyEvidence} />);
    expect(screen.getByText(/No evidence/i)).toBeInTheDocument();
  });

  it("groups excerpts by source", () => {
    const multiSourceEvidence: StoryEvidence = {
      ...mockEvidence,
      source_stats: { intercom: 1, coda: 1 },
      excerpts: [
        {
          text: "From Intercom",
          source: "intercom",
          timestamp: "2024-01-01T00:00:00Z",
        },
        {
          text: "From Coda",
          source: "coda",
          timestamp: "2024-01-01T00:00:00Z",
        },
      ],
    };
    render(<EvidenceBrowser evidence={multiSourceEvidence} />);
    expect(screen.getByText(/From Intercom/)).toBeInTheDocument();
  });
});

describe("Source-aware URLs", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv, NEXT_PUBLIC_CODA_DOC_ID: "test-doc-id" };
  });

  afterEach(() => {
    process.env = originalEnv;
  });

  it("renders Intercom link for intercom excerpts", () => {
    const intercomEvidence: StoryEvidence = {
      ...mockEvidence,
      excerpts: [
        {
          text: "From Intercom",
          source: "intercom",
          conversation_id: "12345",
          timestamp: "2024-01-01T00:00:00Z",
        },
      ],
    };
    render(<EvidenceBrowser evidence={intercomEvidence} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute(
      "href",
      expect.stringContaining("app.intercom.com"),
    );
    expect(link).toHaveAttribute("title", "Open in Intercom");
  });

  it("renders Coda link for coda row excerpts", () => {
    const codaEvidence: StoryEvidence = {
      ...mockEvidence,
      source_stats: { coda: 1 },
      excerpts: [
        {
          text: "From Coda research",
          source: "coda",
          conversation_id: "coda_row_table123_row456",
          timestamp: "2024-01-01T00:00:00Z",
        },
      ],
    };
    render(<EvidenceBrowser evidence={codaEvidence} />);

    // Need to expand the coda section first
    const codaHeader = screen.getByText("Coda");
    fireEvent.click(codaHeader);

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", expect.stringContaining("coda.io"));
    expect(link).toHaveAttribute("title", "Open in Coda");
  });
});
