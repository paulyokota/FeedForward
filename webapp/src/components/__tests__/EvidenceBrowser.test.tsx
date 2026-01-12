/**
 * Minimal tests for EvidenceBrowser
 */

import { render, screen } from "@testing-library/react";
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
