/**
 * Minimal tests for LabelPicker
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LabelPicker } from "../LabelPicker";

// Mock the API
jest.mock("@/lib/api", () => ({
  api: {
    labels: {
      list: jest.fn().mockResolvedValue({
        labels: [
          { id: "1", label_name: "bug", source: "shortcut" },
          { id: "2", label_name: "feature", source: "internal" },
        ],
        total: 2,
        shortcut_count: 1,
        internal_count: 1,
      }),
      create: jest.fn().mockResolvedValue({
        label_name: "new-label",
        source: "internal",
      }),
    },
  },
}));

describe("LabelPicker", () => {
  const mockOnLabelsChange = jest.fn();

  beforeEach(() => {
    mockOnLabelsChange.mockClear();
  });

  it("renders with selected labels", () => {
    render(
      <LabelPicker
        selectedLabels={["bug", "feature"]}
        onLabelsChange={mockOnLabelsChange}
      />,
    );
    expect(screen.getByText("bug")).toBeInTheDocument();
    expect(screen.getByText("feature")).toBeInTheDocument();
  });

  it("renders add labels button when empty", () => {
    render(
      <LabelPicker selectedLabels={[]} onLabelsChange={mockOnLabelsChange} />,
    );
    expect(screen.getByText(/Add labels/i)).toBeInTheDocument();
  });

  it("opens dropdown on click", async () => {
    const user = userEvent.setup();
    render(
      <LabelPicker selectedLabels={[]} onLabelsChange={mockOnLabelsChange} />,
    );

    await user.click(screen.getByText(/Add labels/i));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Search/i)).toBeInTheDocument();
    });
  });
});
