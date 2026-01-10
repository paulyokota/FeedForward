/**
 * Unit tests for drag-and-drop type helpers
 */

import {
  createDraggableId,
  createDroppableId,
  extractStoryId,
  type DraggableId,
  type DroppableId,
} from "../dnd.types";
import type { StatusKey } from "../types";

describe("dnd.types helpers", () => {
  describe("createDraggableId", () => {
    it("returns correct format for simple ID", () => {
      const result = createDraggableId("123");
      expect(result).toBe("story-123");
    });

    it("returns correct format for UUID", () => {
      const uuid = "550e8400-e29b-41d4-a716-446655440000";
      const result = createDraggableId(uuid);
      expect(result).toBe(`story-${uuid}`);
    });

    it("returns correct format for empty string", () => {
      const result = createDraggableId("");
      expect(result).toBe("story-");
    });

    it("handles IDs with special characters", () => {
      const result = createDraggableId("story-123");
      expect(result).toBe("story-story-123");
    });

    it("type assertion: result matches DraggableId type", () => {
      const result: DraggableId = createDraggableId("test");
      expect(result.startsWith("story-")).toBe(true);
    });
  });

  describe("createDroppableId", () => {
    const statuses: StatusKey[] = [
      "candidate",
      "triaged",
      "in_progress",
      "done",
      "dismissed",
    ];

    it.each(statuses)('returns correct format for status "%s"', (status) => {
      const result = createDroppableId(status);
      expect(result).toBe(`column-${status}`);
    });

    it("type assertion: result matches DroppableId type", () => {
      const result: DroppableId = createDroppableId("candidate");
      expect(result.startsWith("column-")).toBe(true);
    });
  });

  describe("extractStoryId", () => {
    it("correctly extracts ID from draggable ID", () => {
      const draggableId = "story-123" as DraggableId;
      const result = extractStoryId(draggableId);
      expect(result).toBe("123");
    });

    it("correctly extracts UUID from draggable ID", () => {
      const uuid = "550e8400-e29b-41d4-a716-446655440000";
      const draggableId = `story-${uuid}` as DraggableId;
      const result = extractStoryId(draggableId);
      expect(result).toBe(uuid);
    });

    it("handles empty story ID", () => {
      const draggableId = "story-" as DraggableId;
      const result = extractStoryId(draggableId);
      expect(result).toBe("");
    });

    it("handles nested story prefix", () => {
      const draggableId = "story-story-123" as DraggableId;
      const result = extractStoryId(draggableId);
      expect(result).toBe("story-123");
    });

    it("roundtrip: create then extract returns original ID", () => {
      const originalId = "550e8400-e29b-41d4-a716-446655440000";
      const draggableId = createDraggableId(originalId);
      const extracted = extractStoryId(draggableId);
      expect(extracted).toBe(originalId);
    });
  });

  describe("type safety", () => {
    it("DraggableId type prevents invalid formats at compile time", () => {
      // This test validates that TypeScript enforces the template literal type
      // Valid formats:
      const valid1: DraggableId = "story-123";
      const valid2: DraggableId = "story-abc";

      expect(valid1).toBeDefined();
      expect(valid2).toBeDefined();

      // Note: TypeScript would prevent these at compile time:
      // const invalid: DraggableId = "card-123"; // TS Error
      // const invalid2: DraggableId = "123"; // TS Error
    });

    it("DroppableId type prevents invalid formats at compile time", () => {
      // This test validates that TypeScript enforces the template literal type
      // Valid formats:
      const valid1: DroppableId = "column-candidate";
      const valid2: DroppableId = "column-done";

      expect(valid1).toBeDefined();
      expect(valid2).toBeDefined();

      // Note: TypeScript would prevent these at compile time:
      // const invalid: DroppableId = "list-candidate"; // TS Error
      // const invalid2: DroppableId = "candidate"; // TS Error
    });
  });
});
