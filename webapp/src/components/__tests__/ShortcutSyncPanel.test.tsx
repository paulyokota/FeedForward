/**
 * Minimal tests for ShortcutSyncPanel
 */

import { render, screen, waitFor } from "@testing-library/react";
import { ShortcutSyncPanel } from "../ShortcutSyncPanel";
import type { SyncStatusResponse } from "@/lib/types";

const mockSyncStatus: SyncStatusResponse = {
  story_id: "test-123",
  shortcut_story_id: "sc-456",
  last_internal_update_at: "2024-01-01T00:00:00Z",
  last_external_update_at: "2024-01-01T00:00:00Z",
  last_synced_at: "2024-01-01T00:00:00Z",
  last_sync_status: "success",
  last_sync_error: null,
  last_sync_direction: "push",
  needs_sync: false,
  sync_direction_hint: null,
};

// Mock the API
jest.mock("@/lib/api", () => ({
  api: {
    sync: {
      getStatus: jest.fn().mockResolvedValue({
        story_id: "test-123",
        shortcut_story_id: "sc-456",
        last_internal_update_at: "2024-01-01T00:00:00Z",
        last_external_update_at: "2024-01-01T00:00:00Z",
        last_synced_at: "2024-01-01T00:00:00Z",
        last_sync_status: "success",
        last_sync_error: null,
        last_sync_direction: "push",
        needs_sync: false,
        sync_direction_hint: null,
      }),
      push: jest.fn().mockResolvedValue({ success: true }),
      pull: jest.fn().mockResolvedValue({ success: true }),
    },
  },
}));

describe("ShortcutSyncPanel", () => {
  it("renders with initial sync status", () => {
    render(
      <ShortcutSyncPanel
        storyId="test-123"
        initialSyncStatus={mockSyncStatus}
      />,
    );
    // Should show synced state (green dot)
    expect(screen.getByTitle("Synced")).toBeInTheDocument();
  });

  it("renders loading state when no initial status", () => {
    render(<ShortcutSyncPanel storyId="test-123" />);
    expect(screen.getByText(/Loading/i)).toBeInTheDocument();
  });

  it("fetches status and renders after loading", async () => {
    render(<ShortcutSyncPanel storyId="test-123" />);

    await waitFor(() => {
      expect(screen.getByTitle("Synced")).toBeInTheDocument();
    });
  });

  it("shows Shortcut link when linked", () => {
    render(
      <ShortcutSyncPanel
        storyId="test-123"
        initialSyncStatus={mockSyncStatus}
      />,
    );

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute(
      "href",
      expect.stringContaining("shortcut.com"),
    );
  });

  it("shows sync action buttons", () => {
    render(
      <ShortcutSyncPanel
        storyId="test-123"
        initialSyncStatus={mockSyncStatus}
      />,
    );

    expect(
      screen.getByRole("button", { name: /Sync Now/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Refresh from Shortcut/i }),
    ).toBeInTheDocument();
  });
});
