import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { StructuredDescription } from "../StructuredDescription";

describe("StructuredDescription", () => {
  it("renders structured view with sections", () => {
    const description = `## Summary

This is a summary section.

## Impact

- High priority
- Affects many users

## Evidence

User feedback from multiple sources.`;

    render(<StructuredDescription description={description} />);

    expect(screen.getByText("Summary")).toBeTruthy();
    expect(screen.getByText("Impact")).toBeTruthy();
    expect(screen.getByText("Evidence")).toBeTruthy();
    expect(screen.getByText("This is a summary section.")).toBeTruthy();
  });

  it("falls back to raw view for unstructured content", () => {
    const description = "Just plain text without any structured sections.";

    render(<StructuredDescription description={description} />);

    // Should only show copy button, no toggle
    expect(screen.getByText("Copy")).toBeTruthy();
    expect(screen.queryByText("Structured")).toBeNull();
    expect(screen.queryByText("Raw")).toBeNull();
  });

  it("allows toggling between structured and raw view", () => {
    const description = `## Summary

Test content.`;

    render(<StructuredDescription description={description} />);

    // Should show toggle buttons
    const structuredBtn = screen.getByText("Structured");
    const rawBtn = screen.getByText("Raw");

    expect(structuredBtn).toBeTruthy();
    expect(rawBtn).toBeTruthy();

    // Click raw button
    fireEvent.click(rawBtn);

    // Should show raw text with ## header
    expect(screen.getByText(/## Summary/)).toBeTruthy();
  });

  it("shows expand button for long sections", () => {
    const description = `## Summary

Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7`;

    render(<StructuredDescription description={description} />);

    // Should show expand button (triggers at >5 lines)
    expect(screen.getByText(/Show .+ more line/)).toBeTruthy();
  });

  it("expands long sections when clicked", () => {
    const description = `## Summary

Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7`;

    render(<StructuredDescription description={description} />);

    const expandBtn = screen.getByText(/Show .+ more line/);
    fireEvent.click(expandBtn);

    // Should show "Show less" button
    expect(screen.getByText("Show less")).toBeTruthy();
  });

  it("copies description to clipboard", async () => {
    const description = "Test description";

    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: jest.fn().mockResolvedValue(undefined),
      },
    });

    render(<StructuredDescription description={description} />);

    const copyBtn = screen.getByText("Copy");
    fireEvent.click(copyBtn);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(description);
  });

  it("renders bullet points correctly", () => {
    const description = `## Details

- Feature 1
- Feature 2
• Feature 3`;

    render(<StructuredDescription description={description} />);

    expect(screen.getByText("Feature 1")).toBeTruthy();
    expect(screen.getByText("Feature 2")).toBeTruthy();
    expect(screen.getByText("Feature 3")).toBeTruthy();
  });

  it("parses ## markdown headers", () => {
    const description = `## User Story

As a user I want to do something.

## Context

Some context here.

## Acceptance Criteria

- [ ] First criterion
- [x] Second criterion (done)`;

    render(<StructuredDescription description={description} />);

    expect(screen.getByText("User Story")).toBeTruthy();
    expect(screen.getByText("Context")).toBeTruthy();
    expect(screen.getByText("Acceptance Criteria")).toBeTruthy();
    expect(screen.getByText("As a user I want to do something.")).toBeTruthy();
  });

  it("renders checkboxes correctly", () => {
    const description = `## Acceptance Criteria

- [ ] Unchecked item
- [x] Checked item`;

    render(<StructuredDescription description={description} />);

    // Should render checkbox indicators
    expect(screen.getByText("○")).toBeTruthy(); // Unchecked
    expect(screen.getByText("✓")).toBeTruthy(); // Checked
    expect(screen.getByText("Unchecked item")).toBeTruthy();
    expect(screen.getByText("Checked item")).toBeTruthy();
  });

  it("renders unicode checkboxes from legacy data", () => {
    const description = `## INVEST Check

✓ Independent: Can be worked on alone
✗ Small: Too large, needs splitting
○ Testable: Needs more criteria`;

    render(<StructuredDescription description={description} />);

    expect(screen.getByText("✓")).toBeTruthy();
    expect(screen.getByText("✗")).toBeTruthy();
    expect(screen.getByText("○")).toBeTruthy();
    expect(screen.getByText(/Independent/)).toBeTruthy();
  });

  it("collapses AI Agent sections by default", () => {
    const description = `## User Story

As a user I want something.

## SECTION 2: AI Agent Task Specification

## Role & Context

This is for an AI agent.

## Instructions (Step-by-Step)

1. Do this
2. Do that`;

    render(<StructuredDescription description={description} />);

    // Human section should be visible
    expect(screen.getByText("User Story")).toBeTruthy();

    // AI Agent section should be collapsed (show the group header)
    expect(screen.getByText("AI Agent Specification")).toBeTruthy();
    expect(screen.getByText(/sections/)).toBeTruthy();

    // Content inside should NOT be visible until expanded
    expect(screen.queryByText("This is for an AI agent.")).toBeNull();
  });

  it("expands AI Agent section when clicked", () => {
    const description = `## User Story

As a user I want something.

## SECTION 2: AI Agent Task Specification

## Role & Context

This is for an AI agent.`;

    render(<StructuredDescription description={description} />);

    // Click to expand
    const groupHeader = screen.getByText("AI Agent Specification");
    fireEvent.click(groupHeader);

    // Now content should be visible
    expect(screen.getByText("Role & Context")).toBeTruthy();
    expect(screen.getByText("This is for an AI agent.")).toBeTruthy();
  });

  it("renders bold text within content", () => {
    const description = `## Context

- **Product Area**: scheduling
- **Component**: pin_scheduler`;

    render(<StructuredDescription description={description} />);

    // Bold text should be rendered (check for the text content)
    expect(screen.getByText(/Product Area/)).toBeTruthy();
    expect(screen.getByText(/scheduling/)).toBeTruthy();
  });
});
