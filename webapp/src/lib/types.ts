// Story Tracking Types - matching FastAPI backend models

// =============================================================================
// Code Context Types (from classification-guided exploration)
// Must be defined before Story which uses CodeContext
// =============================================================================

export interface CodeContextClassification {
  category: string;
  confidence: "high" | "medium" | "low";
  reasoning: string;
  keywords_matched: string[];
}

export interface CodeContextFile {
  path: string;
  line_start: number | null;
  line_end: number | null;
  relevance: string;
}

export interface CodeContextSnippet {
  file_path: string;
  line_start: number;
  line_end: number;
  content: string;
  language: string;
  context: string;
}

export interface CodeContext {
  classification: CodeContextClassification | null;
  relevant_files: CodeContextFile[];
  code_snippets: CodeContextSnippet[];
  exploration_duration_ms: number;
  classification_duration_ms: number;
  explored_at: string | null;
  success: boolean;
  error: string | null;
}

// =============================================================================
// Story Types
// =============================================================================

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
  // Multi-factor scores (Issue #188)
  actionability_score: number | null;
  fix_size_score: number | null;
  severity_score: number | null;
  churn_risk_score: number | null;
  score_metadata: Record<string, unknown> | null;
  code_context: CodeContext | null;
  evidence_count: number;
  conversation_count: number;
  excerpt_count: number; // Issue #197: Number of evidence excerpts
  created_at: string;
  updated_at: string;
}

// Issue #197: Evidence quality thresholds
export const EVIDENCE_QUALITY = {
  LOW_THRESHOLD: 3, // Stories with < 3 excerpts show warning
};

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
// Sort Types (Issue #188)
// =============================================================================

export type SortKey =
  | "updated_at"
  | "created_at"
  | "confidence_score"
  | "actionability_score"
  | "fix_size_score"
  | "severity_score"
  | "churn_risk_score";

export const SORT_CONFIG: Record<
  SortKey,
  { label: string; description: string }
> = {
  updated_at: {
    label: "Recently Updated",
    description: "Most recent activity",
  },
  created_at: {
    label: "Recently Created",
    description: "Newest stories first",
  },
  confidence_score: {
    label: "Confidence",
    description: "Clustering coherence",
  },
  actionability_score: {
    label: "Actionability",
    description: "Ready to implement",
  },
  fix_size_score: {
    label: "Fix Size",
    description: "Higher = more complex fix",
  },
  severity_score: { label: "Severity", description: "Business impact" },
  churn_risk_score: {
    label: "Churn Risk",
    description: "Customer retention risk",
  },
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

// =============================================================================
// Research Search Types
// =============================================================================

export type ResearchSourceType = "coda_page" | "coda_theme" | "intercom";

export interface SearchResult {
  id: string;
  source_type: ResearchSourceType;
  source_id: string;
  title: string;
  snippet: string;
  similarity: number;
  url: string;
  metadata: Record<string, unknown>;
}

export type SuggestedEvidenceStatus = "suggested" | "accepted" | "rejected";

export interface SuggestedEvidence extends SearchResult {
  status: SuggestedEvidenceStatus;
}

export interface ResearchSearchRequest {
  query: string;
  limit?: number;
  source_types?: ResearchSourceType[];
}

export interface SimilarContentRequest {
  source_type: ResearchSourceType;
  source_id: string;
  limit?: number;
}

// =============================================================================
// Pipeline Types
// =============================================================================

export type PipelineRunStatus =
  | "running"
  | "stopping"
  | "stopped"
  | "completed"
  | "failed";

export type PipelinePhase =
  | "classification"
  | "theme_extraction"
  | "pm_review"
  | "story_creation"
  | "completed";

export interface PipelineRunRequest {
  days?: number;
  max_conversations?: number;
  dry_run?: boolean;
  concurrency?: number;
  auto_create_stories?: boolean;
}

export interface PipelineRunResponse {
  run_id: number;
  status: "started" | "queued";
  message: string;
}

export interface PipelineError {
  phase: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface PipelineStatus {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: PipelineRunStatus;
  error_message: string | null;
  date_from: string | null;
  date_to: string | null;
  conversations_fetched: number;
  conversations_filtered: number;
  conversations_classified: number;
  conversations_stored: number;
  duration_seconds: number | null;
  // Hybrid pipeline fields
  current_phase: PipelinePhase | null;
  auto_create_stories: boolean;
  themes_extracted: number;
  themes_new: number;
  themes_filtered: number; // #104: Themes filtered by quality gates
  stories_created: number;
  orphans_created: number;
  stories_ready: boolean;
  // Error tracking (#104)
  errors: PipelineError[];
  warnings: string[];
}

export interface PipelineRunListItem {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  conversations_fetched: number;
  conversations_classified: number;
  conversations_stored: number;
  duration_seconds: number | null;
  // Hybrid pipeline fields (from migration 009)
  current_phase: PipelinePhase | null;
  themes_extracted: number;
  stories_created: number;
  stories_ready: boolean;
  error_count: number; // #104: Number of errors
}

export interface PipelineStopResponse {
  run_id: number;
  status: "stopping" | "stopped" | "not_running";
  message: string;
}

export interface PipelineActiveResponse {
  active: boolean;
  run_id: number | null;
}

// Source type display config
export const SOURCE_TYPE_CONFIG: Record<
  ResearchSourceType,
  { label: string; color: string; bgColor: string }
> = {
  coda_page: {
    label: "Coda Research",
    color: "hsl(217, 91%, 60%)",
    bgColor: "hsla(217, 91%, 60%, 0.15)",
  },
  coda_theme: {
    label: "Coda Theme",
    color: "hsl(258, 90%, 66%)",
    bgColor: "hsla(258, 90%, 66%, 0.15)",
  },
  intercom: {
    label: "Intercom Support",
    color: "hsl(160, 64%, 52%)",
    bgColor: "hsla(160, 64%, 52%, 0.15)",
  },
};

// =============================================================================
// Dry Run Preview Types
// =============================================================================

export interface DryRunSample {
  conversation_id: string;
  snippet: string;
  conversation_type: string;
  confidence: string;
  themes: string[];
  has_support_response: boolean;
}

export interface DryRunClassificationBreakdown {
  by_type: Record<string, number>;
  by_confidence: Record<string, number>;
}

export interface DryRunPreview {
  run_id: number;
  classification_breakdown: DryRunClassificationBreakdown;
  samples: DryRunSample[];
  top_themes: [string, number][];
  total_classified: number;
  timestamp: string;
}

// =============================================================================
// Discovery Types (Issue #223)
// =============================================================================

export interface DiscoveryRun {
  id: string;
  status: string;
  current_stage: string | null;
  parent_run_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  opportunity_count: number;
  stages_completed: number;
}

export interface DiscoveryRunDetail extends DiscoveryRun {
  stages: DiscoveryStage[];
}

export interface DiscoveryStage {
  id: number;
  stage: string;
  status: string;
  attempt_number: number;
  started_at: string | null;
  completed_at: string | null;
  sent_back_from: string | null;
  send_back_reason: string | null;
}

export interface RankedOpportunity {
  index: number;
  opportunity_id: string;
  problem_statement: string;
  affected_area: string;
  recommended_rank: number;
  rationale: string;
  effort_estimate: string;
  build_experiment_decision: string;
  evidence_count: number;
  review_status: string | null;
}

export interface OpportunityDetail {
  index: number;
  opportunity_id: string;
  exploration: Record<string, unknown> | null;
  opportunity_brief: Record<string, unknown> | null;
  solution_brief: Record<string, unknown> | null;
  tech_spec: Record<string, unknown> | null;
  priority_rationale: Record<string, unknown> | null;
  review_decision: Record<string, unknown> | null;
}

export interface ReviewDecisionRequest {
  decision: string;
  reasoning: string;
  adjusted_priority?: number;
  send_back_to_stage?: string;
}

export type ReviewDecisionType =
  | "accepted"
  | "rejected"
  | "deferred"
  | "sent_back"
  | "priority_adjusted";

export const REVIEW_DECISION_CONFIG: Record<
  ReviewDecisionType,
  { label: string; color: string }
> = {
  accepted: { label: "Accepted", color: "var(--accent-green)" },
  rejected: { label: "Rejected", color: "var(--accent-red)" },
  deferred: { label: "Deferred", color: "var(--accent-amber)" },
  sent_back: { label: "Sent Back", color: "var(--accent-purple, #a78bfa)" },
  priority_adjusted: {
    label: "Priority Adjusted",
    color: "var(--accent-blue)",
  },
};
