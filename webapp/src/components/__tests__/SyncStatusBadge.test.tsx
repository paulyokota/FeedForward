/**
 * Minimal tests for SyncStatusBadge
 */

import { render, screen } from "@testing-library/react";
import { SyncStatusBadge } from "../SyncStatusBadge";

describe("SyncStatusBadge", () => {
  it("renders synced state", () => {
    render(<SyncStatusBadge state="synced" showLabel />);
    expect(screen.getByText("Synced")).toBeInTheDocument();
  });

  it("renders pending state", () => {
    render(<SyncStatusBadge state="pending" showLabel />);
    expect(screen.getByText("Pending")).toBeInTheDocument();
  });

  it("renders unsynced state", () => {
    render(<SyncStatusBadge state="unsynced" showLabel />);
    expect(screen.getByText("Not synced")).toBeInTheDocument();
  });

  it("renders error state", () => {
    render(<SyncStatusBadge state="error" showLabel />);
    expect(screen.getByText("Error")).toBeInTheDocument();
  });
});
