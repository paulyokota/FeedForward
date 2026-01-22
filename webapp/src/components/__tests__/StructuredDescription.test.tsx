import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { StructuredDescription } from "../StructuredDescription";

describe("StructuredDescription", () => {
  it("renders structured view with sections", () => {
    const description = `**Summary**
This is a summary section.

**Impact**
- High priority
- Affects many users

**Evidence**
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
    const description = `**Summary**
Test content.`;

    render(<StructuredDescription description={description} />);

    // Should show toggle buttons
    const structuredBtn = screen.getByText("Structured");
    const rawBtn = screen.getByText("Raw");

    expect(structuredBtn).toBeTruthy();
    expect(rawBtn).toBeTruthy();

    // Click raw button
    fireEvent.click(rawBtn);

    // Should show raw text
    expect(screen.getByText(/\*\*Summary\*\*/)).toBeTruthy();
  });

  it("shows expand button for long sections", () => {
    const description = `**Summary**
Line 1
Line 2
Line 3
Line 4
Line 5
Line 6
Line 7`;

    render(<StructuredDescription description={description} />);

    // Should show expand button (now triggers at >5 lines)
    expect(screen.getByText(/Show .+ more line/)).toBeTruthy();
  });

  it("expands long sections when clicked", () => {
    const description = `**Summary**
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
    // Using "Details" which is a known section header
    const description = `**Details**
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
});
