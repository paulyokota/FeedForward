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
  | "draft"
  | "candidate"
  | "triaged"
  | "in_progress"
  | "done"
  | "dismissed";

export const STATUS_ORDER: StatusKey[] = [
  "draft",
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
  draft: { label: "Draft", color: "var(--status-draft)" },
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

// =============================================================================
// Sync Types
// =============================================================================

export interface SyncStatusResponse {
  story_id: string;
  shortcut_story_id: string | null;
  last_internal_update_at: string | null;
  last_external_update_at: string | null;
  last_synced_at: string | null;
  last_sync_status: "success" | "failed" | "pending" | null;
  last_sync_error: string | null;
  last_sync_direction: "push" | "pull" | null;
  needs_sync: boolean;
  sync_direction_hint: "push" | "pull" | null;
}

export interface StorySnapshot {
  title: string;
  description: string | null;
  labels: string[];
  priority: string | null;
  severity: string | null;
  product_area: string | null;
  technical_area: string | null;
}

export interface PushResponse {
  shortcut_story_id: string;
  last_synced_at: string;
  sync_status: string;
}

export interface PullResponse {
  story_id: string;
  snapshot: StorySnapshot;
  last_synced_at: string;
  sync_status: string;
}

export interface SyncResult {
  success: boolean;
  direction: "push" | "pull" | "none";
  story_id: string;
  shortcut_story_id: string | null;
  error: string | null;
  synced_at: string | null;
}

export type SyncState = "synced" | "pending" | "unsynced" | "error";

// =============================================================================
// Label Types
// =============================================================================

export interface LabelRegistryEntry {
  label_name: string;
  source: "shortcut" | "internal";
  category: string | null;
  created_at: string;
  last_seen_at: string;
}

export interface LabelListResponse {
  labels: LabelRegistryEntry[];
  total: number;
  shortcut_count: number;
  internal_count: number;
}

export interface LabelCreate {
  label_name: string;
  source?: "shortcut" | "internal";
  category?: string;
}

export interface ImportResult {
  imported_count: number;
  skipped_count: number;
  updated_count: number;
  errors: string[];
}

// =============================================================================
// Analytics Types
// =============================================================================

export interface StoryMetricsResponse {
  total_stories: number;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  by_severity: Record<string, number>;
  by_product_area: Record<string, number>;
  created_last_7_days: number;
  created_last_30_days: number;
  avg_confidence_score: number | null;
  total_evidence_count: number;
  total_conversation_count: number;
}

export interface ThemeTrendResponse {
  theme_signature: string;
  product_area: string;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  trend_direction: "rising" | "stable" | "declining";
  linked_story_count: number;
}

export interface SourceDistributionResponse {
  source: string;
  conversation_count: number;
  story_count: number;
  percentage: number;
}

export interface EvidenceSummaryResponse {
  total_evidence_records: number;
  total_conversations_linked: number;
  total_themes_linked: number;
  sources: SourceDistributionResponse[];
}

export interface SyncMetricsResponse {
  total_synced: number;
  success_count: number;
  error_count: number;
  push_count: number;
  pull_count: number;
  unsynced_count: number;
}

// =============================================================================
// Sync State Helpers
// =============================================================================

export const SYNC_STATE_CONFIG: Record<
  SyncState,
  { label: string; color: string }
> = {
  synced: { label: "Synced", color: "var(--accent-green)" },
  pending: { label: "Pending", color: "var(--accent-amber)" },
  unsynced: { label: "Not synced", color: "var(--text-tertiary)" },
  error: { label: "Error", color: "var(--accent-red)" },
};

export function getSyncState(syncStatus: string | null | undefined): SyncState {
  if (!syncStatus) return "unsynced";
  if (syncStatus === "failed" || syncStatus === "error") return "error";
  if (syncStatus === "pending") return "pending";
  if (syncStatus === "success") return "synced";
  return "unsynced";
}
