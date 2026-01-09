// API Client for Story Tracking backend

import type {
  Story,
  StoryWithEvidence,
  StoryListResponse,
  BoardView,
  StoryUpdate,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetcher<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new ApiError(response.status, `API error: ${response.statusText}`);
  }

  return response.json();
}

// Story endpoints
export const api = {
  stories: {
    list: async (params?: {
      status?: string;
      product_area?: string;
      limit?: number;
      offset?: number;
    }): Promise<StoryListResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.status) searchParams.set("status", params.status);
      if (params?.product_area)
        searchParams.set("product_area", params.product_area);
      if (params?.limit) searchParams.set("limit", params.limit.toString());
      if (params?.offset) searchParams.set("offset", params.offset.toString());

      const query = searchParams.toString();
      return fetcher(`/api/stories${query ? `?${query}` : ""}`);
    },

    board: async (): Promise<BoardView> => {
      return fetcher("/api/stories/board");
    },

    get: async (id: string): Promise<StoryWithEvidence> => {
      return fetcher(`/api/stories/${id}`);
    },

    search: async (query: string, limit = 20): Promise<Story[]> => {
      return fetcher(
        `/api/stories/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      );
    },

    update: async (id: string, updates: StoryUpdate): Promise<Story> => {
      return fetcher(`/api/stories/${id}`, {
        method: "PATCH",
        body: JSON.stringify(updates),
      });
    },

    create: async (story: Partial<Story>): Promise<Story> => {
      return fetcher("/api/stories", {
        method: "POST",
        body: JSON.stringify(story),
      });
    },

    delete: async (id: string): Promise<void> => {
      await fetcher(`/api/stories/${id}`, { method: "DELETE" });
    },
  },

  comments: {
    create: async (
      storyId: string,
      body: string,
      author?: string,
    ): Promise<{
      id: string;
      body: string;
      author: string | null;
      created_at: string;
    }> => {
      return fetcher(`/api/stories/${storyId}/comments`, {
        method: "POST",
        body: JSON.stringify({ body, author }),
      });
    },
  },

  health: {
    check: async (): Promise<{ status: string }> => {
      return fetcher("/health");
    },
  },
};

export { ApiError };
