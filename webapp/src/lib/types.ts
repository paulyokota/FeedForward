// Story Tracking Types - matching FastAPI backend models

export interface Story {
  id: string;
  title: string;
  description: string | null;
  labels: string[];
  priority: "urgent" | "high" | "medium" | "low" | null;
  severity: "critical" | "major" | "moderate" | "minor" | null;
  product_area: string | null;
  technical_area: string | null;
  status: string;
  confidence_score: number | null;
  evidence_count: number;
  conversation_count: number;
  created_at: string;
  updated_at: string;
}

export interface EvidenceExcerpt {
  text: string;
  source: "intercom" | "coda" | string;
  conversation_id: string | null;
}

export interface StoryEvidence {
  id: string;
  story_id: string;
  conversation_ids: string[];
  theme_signatures: string[];
  source_stats: Record<string, number>;
  excerpts: EvidenceExcerpt[];
  created_at: string;
  updated_at: string;
}

export interface StoryComment {
  id: string;
  story_id: string;
  external_id: string | null;
  source: "internal" | "shortcut";
  body: string;
  author: string | null;
  created_at: string;
}

export interface SyncMetadata {
  story_id: string;
  shortcut_story_id: string | null;
  last_internal_update_at: string | null;
  last_external_update_at: string | null;
  last_synced_at: string | null;
  last_sync_status: "success" | "failed" | "pending" | null;
  last_sync_error: string | null;
  last_sync_direction: "push" | "pull" | null;
}

export interface StoryWithEvidence extends Story {
  evidence: StoryEvidence | null;
  sync: SyncMetadata | null;
  comments: StoryComment[];
}

export interface StoryListResponse {
  stories: Story[];
  total: number;
  limit: number;
  offset: number;
}

export type BoardView = Record<string, Story[]>;

export interface StoryUpdate {
  title?: string;
  description?: string;
  labels?: string[];
  priority?: string | null;
  severity?: string | null;
  product_area?: string | null;
  technical_area?: string | null;
  status?: string;
  confidence_score?: number | null;
}

// UI-specific types
export type PriorityKey = "urgent" | "high" | "medium" | "low";

export type StatusKey =
  | "candidate"
  | "triaged"
  | "in_progress"
  | "done"
  | "dismissed";

export const STATUS_ORDER: StatusKey[] = [
  "candidate",
  "triaged",
  "in_progress",
  "done",
  "dismissed",
];

export const STATUS_CONFIG: Record<
  StatusKey,
  { label: string; color: string }
> = {
  candidate: { label: "Candidate", color: "var(--status-candidate)" },
  triaged: { label: "Triaged", color: "var(--status-triaged)" },
  in_progress: { label: "In Progress", color: "var(--status-in-progress)" },
  done: { label: "Done", color: "var(--status-done)" },
  dismissed: { label: "Dismissed", color: "var(--status-dismissed)" },
};

export const PRIORITY_CONFIG: Record<string, { label: string; color: string }> =
  {
    urgent: { label: "Urgent", color: "var(--priority-urgent)" },
    high: { label: "High", color: "var(--priority-high)" },
    medium: { label: "Medium", color: "var(--priority-medium)" },
    low: { label: "Low", color: "var(--priority-low)" },
  };
