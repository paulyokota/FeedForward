// API Client for Story Tracking backend

import type {
  Story,
  StoryWithEvidence,
  StoryListResponse,
  BoardView,
  StoryUpdate,
  SyncStatusResponse,
  StorySnapshot,
  PushResponse,
  PullResponse,
  SyncResult,
  LabelRegistryEntry,
  LabelListResponse,
  LabelCreate,
  ImportResult,
  StoryMetricsResponse,
  ThemeTrendResponse,
  SourceDistributionResponse,
  EvidenceSummaryResponse,
  SyncMetricsResponse,
  SearchResult,
  SuggestedEvidence,
  ResearchSourceType,
  PipelineRunRequest,
  PipelineRunResponse,
  PipelineStatus,
  PipelineRunListItem,
  PipelineStopResponse,
  PipelineActiveResponse,
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
      created_since?: string;
      limit?: number;
      offset?: number;
    }): Promise<StoryListResponse> => {
      const searchParams = new URLSearchParams();
      if (params?.status) searchParams.set("status", params.status);
      if (params?.product_area)
        searchParams.set("product_area", params.product_area);
      if (params?.created_since)
        searchParams.set("created_since", params.created_since);
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

  // Sync endpoints
  sync: {
    getStatus: async (storyId: string): Promise<SyncStatusResponse> => {
      return fetcher(`/api/sync/shortcut/status/${storyId}`);
    },

    push: async (
      storyId: string,
      snapshot?: StorySnapshot,
    ): Promise<PushResponse> => {
      return fetcher("/api/sync/shortcut/push", {
        method: "POST",
        body: JSON.stringify({ story_id: storyId, snapshot }),
      });
    },

    pull: async (
      shortcutStoryId: string,
      storyId?: string,
    ): Promise<PullResponse> => {
      return fetcher("/api/sync/shortcut/pull", {
        method: "POST",
        body: JSON.stringify({
          shortcut_story_id: shortcutStoryId,
          story_id: storyId,
        }),
      });
    },

    syncStory: async (storyId: string): Promise<SyncResult> => {
      return fetcher(`/api/sync/shortcut/sync/${storyId}`, { method: "POST" });
    },
  },

  // Label endpoints
  labels: {
    list: async (source?: string, limit = 100): Promise<LabelListResponse> => {
      const params = new URLSearchParams();
      if (source) params.set("source", source);
      params.set("limit", limit.toString());
      return fetcher(`/api/labels?${params}`);
    },

    get: async (labelName: string): Promise<LabelRegistryEntry> => {
      return fetcher(`/api/labels/${encodeURIComponent(labelName)}`);
    },

    create: async (label: LabelCreate): Promise<LabelRegistryEntry> => {
      return fetcher("/api/labels", {
        method: "POST",
        body: JSON.stringify(label),
      });
    },

    importFromShortcut: async (): Promise<ImportResult> => {
      return fetcher("/api/labels/import", { method: "POST" });
    },
  },

  // Analytics endpoints
  analytics: {
    getStoryMetrics: async (): Promise<StoryMetricsResponse> => {
      return fetcher("/api/analytics/stories");
    },

    getTrendingThemes: async (
      days = 7,
      limit = 20,
    ): Promise<ThemeTrendResponse[]> => {
      return fetcher(
        `/api/analytics/themes/trending?days=${days}&limit=${limit}`,
      );
    },

    getSourceDistribution: async (): Promise<SourceDistributionResponse[]> => {
      return fetcher("/api/analytics/sources");
    },

    getEvidenceSummary: async (): Promise<EvidenceSummaryResponse> => {
      return fetcher("/api/analytics/evidence");
    },

    getSyncMetrics: async (): Promise<SyncMetricsResponse> => {
      return fetcher("/api/analytics/sync");
    },
  },

  // Research search endpoints
  research: {
    search: async (
      query: string,
      sourceTypes?: ResearchSourceType[],
      limit = 20,
    ): Promise<SearchResult[]> => {
      const params = new URLSearchParams();
      params.set("q", query);
      params.set("limit", limit.toString());
      if (sourceTypes && sourceTypes.length > 0) {
        sourceTypes.forEach((type) => params.append("source_types", type));
      }
      return fetcher(`/api/research/search?${params}`);
    },

    getSimilar: async (
      sourceType: ResearchSourceType,
      sourceId: string,
      limit = 10,
    ): Promise<SearchResult[]> => {
      const params = new URLSearchParams();
      params.set("limit", limit.toString());
      return fetcher(
        `/api/research/similar/${sourceType}/${encodeURIComponent(sourceId)}?${params}`,
      );
    },

    getSuggestedEvidence: async (
      storyId: string,
    ): Promise<SuggestedEvidence[]> => {
      const response = await fetcher<{ suggestions: SuggestedEvidence[] }>(
        `/api/research/stories/${storyId}/suggested-evidence`,
      );
      return response.suggestions;
    },

    acceptEvidence: async (
      storyId: string,
      evidenceId: string,
    ): Promise<{ success: boolean }> => {
      return fetcher(
        `/api/research/stories/${storyId}/suggested-evidence/${encodeURIComponent(evidenceId)}/accept`,
        {
          method: "POST",
        },
      );
    },

    rejectEvidence: async (
      storyId: string,
      evidenceId: string,
    ): Promise<{ success: boolean }> => {
      return fetcher(
        `/api/research/stories/${storyId}/suggested-evidence/${encodeURIComponent(evidenceId)}/reject`,
        {
          method: "POST",
        },
      );
    },
  },

  // Pipeline endpoints
  pipeline: {
    run: async (
      request: PipelineRunRequest = {},
    ): Promise<PipelineRunResponse> => {
      return fetcher("/api/pipeline/run", {
        method: "POST",
        body: JSON.stringify(request),
      });
    },

    status: async (runId: number): Promise<PipelineStatus> => {
      return fetcher(`/api/pipeline/status/${runId}`);
    },

    history: async (limit = 20, offset = 0): Promise<PipelineRunListItem[]> => {
      return fetcher(`/api/pipeline/history?limit=${limit}&offset=${offset}`);
    },

    active: async (): Promise<PipelineActiveResponse> => {
      return fetcher("/api/pipeline/active");
    },

    stop: async (): Promise<PipelineStopResponse> => {
      return fetcher("/api/pipeline/stop", {
        method: "POST",
      });
    },
  },
};

export { ApiError };
