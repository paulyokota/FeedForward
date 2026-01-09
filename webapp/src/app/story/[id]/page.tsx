"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type { StoryWithEvidence, StatusKey, StoryComment } from "@/lib/types";
import { STATUS_CONFIG, PRIORITY_CONFIG, STATUS_ORDER } from "@/lib/types";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";

export default function StoryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [story, setStory] = useState<StoryWithEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [commentText, setCommentText] = useState("");
  const [isSubmittingComment, setIsSubmittingComment] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);

  useEffect(() => {
    async function fetchStory() {
      try {
        const data = await api.stories.get(params.id as string);
        setStory(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load story");
      } finally {
        setLoading(false);
      }
    }
    if (params.id) {
      fetchStory();
    }
  }, [params.id]);

  const handleStatusChange = async (newStatus: string) => {
    if (!story || isUpdating) return;
    setIsUpdating(true);
    try {
      const updated = await api.stories.update(story.id, { status: newStatus });
      setStory((prev) => (prev ? { ...prev, ...updated } : prev));
    } catch (err) {
      console.error("Failed to update status:", err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handlePriorityChange = async (newPriority: string) => {
    if (!story || isUpdating) return;
    setIsUpdating(true);
    try {
      const updated = await api.stories.update(story.id, {
        priority: newPriority || null,
      });
      setStory((prev) => (prev ? { ...prev, ...updated } : prev));
    } catch (err) {
      console.error("Failed to update priority:", err);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleSubmitComment = async () => {
    if (!story || !commentText.trim() || isSubmittingComment) return;
    setIsSubmittingComment(true);
    try {
      const newComment = await api.comments.create(
        story.id,
        commentText.trim(),
      );
      setStory((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          comments: [
            ...(prev.comments || []),
            {
              id: newComment.id,
              story_id: story.id,
              external_id: null,
              source: "internal" as const,
              body: newComment.body,
              author: newComment.author,
              created_at: newComment.created_at,
            },
          ],
        };
      });
      setCommentText("");
    } catch (err) {
      console.error("Failed to add comment:", err);
    } finally {
      setIsSubmittingComment(false);
    }
  };

  if (loading) {
    return (
      <div className="loading-state">
        <div className="spinner" />
        <span>Loading story...</span>
      </div>
    );
  }

  if (error || !story) {
    return (
      <div className="error-state">
        <p>{error || "Story not found"}</p>
        <button onClick={() => router.push("/")}>Back to Board</button>
      </div>
    );
  }

  const statusConfig = STATUS_CONFIG[story.status as StatusKey];
  const priorityConfig = story.priority
    ? PRIORITY_CONFIG[story.priority]
    : null;

  return (
    <div className="detail-page">
      {/* Top Navigation */}
      <header className="top-bar">
        <nav className="breadcrumb">
          <button className="logo-link" onClick={() => router.push("/")}>
            <FeedForwardLogo size="sm" />
          </button>
          <span className="breadcrumb-sep">/</span>
          <button className="breadcrumb-link" onClick={() => router.push("/")}>
            Stories
          </button>
          <span className="breadcrumb-sep">/</span>
          <span className="breadcrumb-current">{story.id.slice(0, 8)}</span>
        </nav>
        <div className="top-actions">
          <ThemeToggle />
          <button className="action-btn">Edit</button>
        </div>
      </header>

      {/* Two-Column Layout */}
      <div className="content-grid">
        {/* Main Content - Left */}
        <main className="main-content">
          {/* Story Header */}
          <section className="story-header">
            <h1 className="story-title">{story.title}</h1>
            {story.description && (
              <div className="story-description">
                <p>{story.description}</p>
              </div>
            )}
          </section>

          {/* Evidence Section */}
          {story.evidence &&
            story.evidence.excerpts &&
            story.evidence.excerpts.length > 0 && (
              <section className="content-section">
                <h2 className="section-title">Evidence</h2>
                <div className="evidence-list">
                  {story.evidence.excerpts.map((excerpt, idx) => (
                    <div key={idx} className="evidence-card">
                      <p className="evidence-text">{excerpt.text}</p>
                      <div className="evidence-meta">
                        <span className="evidence-source">
                          {excerpt.source}
                        </span>
                        {excerpt.conversation_id && (
                          <span className="evidence-id">
                            {excerpt.conversation_id}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}

          {/* Comments Section */}
          <section className="content-section">
            <div className="section-header">
              <h2 className="section-title">Comments</h2>
              <span className="section-count">
                {story.comments?.length || 0}
              </span>
            </div>

            {/* Comment Input */}
            <div className="comment-input-wrapper">
              <textarea
                className="comment-input"
                placeholder="Add a comment..."
                rows={2}
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    handleSubmitComment();
                  }
                }}
              />
              {commentText.trim() && (
                <button
                  className="comment-submit-btn"
                  onClick={handleSubmitComment}
                  disabled={isSubmittingComment}
                >
                  {isSubmittingComment ? "Posting..." : "Post"}
                </button>
              )}
            </div>

            {/* Comments List */}
            <div className="comments-list">
              {story.comments && story.comments.length > 0 ? (
                story.comments.map((comment) => (
                  <div key={comment.id} className="comment-item">
                    <div className="comment-header">
                      <span className="comment-author">
                        {comment.author || "System"}
                      </span>
                      <span className="comment-date">
                        {new Date(comment.created_at).toLocaleDateString(
                          "en-US",
                          {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                            hour: "numeric",
                            minute: "2-digit",
                          },
                        )}
                      </span>
                    </div>
                    <p className="comment-body">{comment.body}</p>
                  </div>
                ))
              ) : (
                <div className="empty-comments">No comments yet</div>
              )}
            </div>
          </section>

          {/* Activity Feed */}
          <section className="content-section">
            <h2 className="section-title">Story Activity</h2>
            <div className="activity-feed">
              <div className="activity-item">
                <div className="activity-dot" />
                <div className="activity-content">
                  <span className="activity-text">Story created</span>
                  <span className="activity-time">
                    {new Date(story.created_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      year: "numeric",
                    })}
                  </span>
                </div>
              </div>
              {story.created_at !== story.updated_at && (
                <div className="activity-item">
                  <div className="activity-dot" />
                  <div className="activity-content">
                    <span className="activity-text">Story updated</span>
                    <span className="activity-time">
                      {new Date(story.updated_at).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </span>
                  </div>
                </div>
              )}
            </div>
          </section>
        </main>

        {/* Sidebar - Right */}
        <aside className="sidebar">
          {/* Story ID */}
          <div className="sidebar-section">
            <div className="field-row">
              <span className="field-label">Story ID</span>
              <span className="field-value mono">{story.id.slice(0, 8)}</span>
            </div>
          </div>

          <div className="sidebar-divider" />

          {/* Core Metadata */}
          <div className="sidebar-section">
            <div className="field-row">
              <span className="field-label">Status</span>
              <div className="field-value">
                <span
                  className="status-dot"
                  style={{ backgroundColor: statusConfig?.color }}
                />
                <select
                  className="inline-select"
                  value={story.status}
                  onChange={(e) => handleStatusChange(e.target.value)}
                  disabled={isUpdating}
                >
                  {STATUS_ORDER.map((status) => (
                    <option key={status} value={status}>
                      {STATUS_CONFIG[status].label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field-row">
              <span className="field-label">Priority</span>
              <div className="field-value">
                <select
                  className="inline-select"
                  value={story.priority || ""}
                  onChange={(e) => handlePriorityChange(e.target.value)}
                  disabled={isUpdating}
                  style={{
                    color: priorityConfig?.color || "var(--text-secondary)",
                  }}
                >
                  <option value="">None</option>
                  {Object.entries(PRIORITY_CONFIG).map(([key, config]) => (
                    <option key={key} value={key}>
                      {config.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="field-row">
              <span className="field-label">Severity</span>
              <span className="field-value">
                {story.severity ? (
                  <span className="severity-value">{story.severity}</span>
                ) : (
                  <span className="field-empty">None</span>
                )}
              </span>
            </div>

            <div className="field-row">
              <span className="field-label">Product Area</span>
              <span className="field-value">
                {story.product_area || (
                  <span className="field-empty">None</span>
                )}
              </span>
            </div>

            <div className="field-row">
              <span className="field-label">Technical Area</span>
              <span className="field-value">
                {story.technical_area || (
                  <span className="field-empty">None</span>
                )}
              </span>
            </div>
          </div>

          <div className="sidebar-divider" />

          {/* Metrics */}
          <div className="sidebar-section">
            <div className="field-row">
              <span className="field-label">Confidence</span>
              <span className="field-value">
                {story.confidence_score !== null ? (
                  <span className="confidence-value">
                    {Math.round(story.confidence_score * 100)}%
                  </span>
                ) : (
                  <span className="field-empty">—</span>
                )}
              </span>
            </div>

            <div className="field-row">
              <span className="field-label">Evidence</span>
              <span className="field-value">{story.evidence_count}</span>
            </div>

            <div className="field-row">
              <span className="field-label">Conversations</span>
              <span className="field-value">{story.conversation_count}</span>
            </div>
          </div>

          <div className="sidebar-divider" />

          {/* Labels */}
          <div className="sidebar-section">
            <span className="field-label standalone">Labels</span>
            {story.labels && story.labels.length > 0 ? (
              <div className="labels-list">
                {story.labels.map((label) => (
                  <span key={label} className="label-tag">
                    {label}
                  </span>
                ))}
              </div>
            ) : (
              <div className="add-labels">
                <button className="add-btn">+ Add Labels</button>
              </div>
            )}
          </div>

          <div className="sidebar-divider" />

          {/* Sync Status */}
          <div className="sidebar-section">
            <span className="field-label standalone">Shortcut Sync</span>
            {story.sync ? (
              <div className="sync-info">
                <div className="field-row compact">
                  <span className="field-label-sm">Story ID</span>
                  <span className="field-value-sm mono">
                    {story.sync.shortcut_story_id || "—"}
                  </span>
                </div>
                <div className="field-row compact">
                  <span className="field-label-sm">Status</span>
                  <span
                    className={`sync-status sync-${story.sync.last_sync_status}`}
                  >
                    {story.sync.last_sync_status || "Not synced"}
                  </span>
                </div>
                {story.sync.last_synced_at && (
                  <div className="field-row compact">
                    <span className="field-label-sm">Last sync</span>
                    <span className="field-value-sm">
                      {new Date(story.sync.last_synced_at).toLocaleDateString()}
                    </span>
                  </div>
                )}
              </div>
            ) : (
              <button className="link-btn">Link to Shortcut</button>
            )}
          </div>

          <div className="sidebar-divider" />

          {/* Timestamps */}
          <div className="sidebar-section timestamps">
            <div className="timestamp-row">
              <span className="timestamp-label">Created</span>
              <span className="timestamp-value">
                {new Date(story.created_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
            </div>
            <div className="timestamp-row">
              <span className="timestamp-label">Last updated</span>
              <span className="timestamp-value">
                {new Date(story.updated_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                })}
              </span>
            </div>
          </div>
        </aside>
      </div>

      <style jsx>{`
        .detail-page {
          min-height: 100vh;
          background: var(--bg-void);
        }

        /* Top Navigation Bar */
        .top-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 24px;
          background: var(--bg-surface);
          border-bottom: 1px solid var(--border-default);
          position: sticky;
          top: 0;
          z-index: 20;
        }

        .breadcrumb {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
        }

        .logo-link {
          background: none;
          border: none;
          cursor: pointer;
          padding: 0;
          display: flex;
          align-items: center;
          opacity: 0.9;
          transition: opacity 0.15s ease;
        }

        .logo-link:hover {
          opacity: 1;
        }

        .breadcrumb-link {
          background: none;
          border: none;
          color: var(--text-secondary);
          cursor: pointer;
          padding: 0;
        }

        .breadcrumb-link:hover {
          color: var(--accent-teal, var(--accent-blue));
        }

        .breadcrumb-sep {
          color: var(--text-muted);
        }

        .breadcrumb-current {
          color: var(--text-primary);
          font-family: var(--font-mono);
        }

        .top-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .action-btn {
          padding: 6px 14px;
          background: var(--bg-elevated);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .action-btn:hover {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        /* Two-Column Grid */
        .content-grid {
          display: grid;
          grid-template-columns: 1fr 320px;
          min-height: calc(100vh - 49px);
        }

        /* Main Content Area */
        .main-content {
          padding: 32px 40px;
          border-right: 1px solid var(--border-subtle);
          overflow-y: auto;
        }

        .story-header {
          margin-bottom: 32px;
        }

        .story-title {
          font-size: 24px;
          font-weight: 600;
          color: var(--text-primary);
          line-height: 1.3;
          margin: 0 0 16px 0;
        }

        .story-description {
          font-size: 15px;
          color: var(--text-secondary);
          line-height: 1.65;
        }

        .story-description p {
          margin: 0;
        }

        /* Content Sections */
        .content-section {
          margin-bottom: 32px;
        }

        .section-header {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 16px;
        }

        .section-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .section-count {
          font-size: 12px;
          color: var(--text-tertiary);
          background: var(--bg-elevated);
          padding: 2px 8px;
          border-radius: 10px;
        }

        /* Evidence */
        .evidence-list {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .evidence-card {
          padding: 16px;
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
        }

        .evidence-text {
          font-size: 14px;
          color: var(--text-primary);
          line-height: 1.6;
          margin: 0 0 12px 0;
        }

        .evidence-meta {
          display: flex;
          gap: 16px;
          font-size: 12px;
          color: var(--text-tertiary);
        }

        .evidence-source {
          text-transform: capitalize;
        }

        .evidence-id {
          font-family: var(--font-mono);
        }

        /* Comments */
        .comment-input-wrapper {
          margin-bottom: 20px;
        }

        .comment-input {
          width: 100%;
          padding: 12px 14px;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-primary);
          font-size: 14px;
          font-family: inherit;
          resize: vertical;
          min-height: 60px;
        }

        .comment-input::placeholder {
          color: var(--text-muted);
        }

        .comment-input:focus {
          outline: none;
          border-color: var(--accent-blue);
        }

        .comment-submit-btn {
          margin-top: 10px;
          padding: 8px 16px;
          background: var(--accent-blue);
          border: none;
          border-radius: var(--radius-md);
          color: white;
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .comment-submit-btn:hover:not(:disabled) {
          background: #74b3ff;
        }

        .comment-submit-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        /* Inline Select for sidebar editing */
        .inline-select {
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-sm);
          color: var(--text-primary);
          font-size: 13px;
          padding: 4px 8px;
          cursor: pointer;
          appearance: none;
          background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E");
          background-repeat: no-repeat;
          background-position: right 6px center;
          padding-right: 24px;
          min-width: 100px;
          transition: all 0.15s ease;
        }

        .inline-select:hover {
          border-color: var(--accent-blue);
        }

        .inline-select:focus {
          outline: none;
          border-color: var(--accent-blue);
          box-shadow: 0 0 0 2px var(--accent-blue-dim);
        }

        .inline-select:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }

        .comments-list {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }

        .comment-item {
          padding: 14px 16px;
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: var(--radius-md);
        }

        .comment-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 8px;
        }

        .comment-author {
          font-size: 13px;
          font-weight: 500;
          color: var(--text-primary);
        }

        .comment-date {
          font-size: 12px;
          color: var(--text-tertiary);
        }

        .comment-body {
          font-size: 14px;
          color: var(--text-secondary);
          line-height: 1.5;
          margin: 0;
        }

        .empty-comments {
          color: var(--text-muted);
          font-size: 14px;
          padding: 24px;
          text-align: center;
          border: 1px dashed var(--border-subtle);
          border-radius: var(--radius-md);
        }

        /* Activity Feed */
        .activity-feed {
          display: flex;
          flex-direction: column;
          gap: 12px;
          padding-left: 12px;
          border-left: 2px solid var(--border-subtle);
        }

        .activity-item {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          position: relative;
        }

        .activity-dot {
          width: 8px;
          height: 8px;
          background: var(--bg-elevated);
          border: 2px solid var(--border-default);
          border-radius: 50%;
          margin-top: 5px;
          margin-left: -17px;
        }

        .activity-content {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .activity-text {
          font-size: 13px;
          color: var(--text-secondary);
        }

        .activity-time {
          font-size: 12px;
          color: var(--text-tertiary);
        }

        /* Sidebar */
        .sidebar {
          padding: 20px;
          background: var(--bg-primary);
          position: sticky;
          top: 49px;
          height: calc(100vh - 49px);
          overflow-y: auto;
        }

        .sidebar-section {
          margin-bottom: 4px;
        }

        .sidebar-divider {
          height: 1px;
          background: var(--border-subtle);
          margin: 16px 0;
        }

        .field-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 0;
        }

        .field-row.compact {
          padding: 4px 0;
        }

        .field-label {
          font-size: 13px;
          color: var(--text-tertiary);
        }

        .field-label.standalone {
          display: block;
          margin-bottom: 10px;
        }

        .field-label-sm {
          font-size: 12px;
          color: var(--text-muted);
        }

        .field-value {
          font-size: 13px;
          color: var(--text-primary);
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .field-value.mono {
          font-family: var(--font-mono);
        }

        .field-value-sm {
          font-size: 12px;
          color: var(--text-secondary);
        }

        .field-value-sm.mono {
          font-family: var(--font-mono);
        }

        .field-empty {
          color: var(--text-muted);
        }

        .status-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }

        .priority-indicator {
          font-weight: 500;
        }

        .severity-value {
          text-transform: capitalize;
        }

        .confidence-value {
          color: var(--accent-green);
          font-weight: 500;
        }

        /* Labels */
        .labels-list {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
        }

        .label-tag {
          font-size: 12px;
          color: var(--accent-purple);
          background: var(--accent-purple-dim);
          padding: 4px 10px;
          border-radius: 4px;
        }

        .add-btn {
          background: none;
          border: none;
          color: var(--text-tertiary);
          font-size: 13px;
          cursor: pointer;
          padding: 0;
        }

        .add-btn:hover {
          color: var(--accent-blue);
        }

        /* Sync Status */
        .sync-info {
          margin-top: 8px;
        }

        .sync-status {
          font-size: 12px;
          font-weight: 500;
        }

        .sync-success {
          color: var(--accent-green);
        }

        .sync-failed {
          color: var(--accent-red);
        }

        .sync-pending {
          color: var(--accent-amber);
        }

        .link-btn {
          margin-top: 8px;
          padding: 8px 14px;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-secondary);
          font-size: 13px;
          cursor: pointer;
          width: 100%;
          transition: all 0.15s ease;
        }

        .link-btn:hover {
          background: var(--bg-elevated);
          color: var(--text-primary);
        }

        /* Timestamps */
        .timestamps {
          font-size: 12px;
        }

        .timestamp-row {
          display: flex;
          flex-direction: column;
          gap: 2px;
          margin-bottom: 8px;
        }

        .timestamp-label {
          color: var(--text-muted);
        }

        .timestamp-value {
          color: var(--text-tertiary);
        }

        /* Loading & Error States */
        .loading-state,
        .error-state {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          gap: 16px;
          color: var(--text-secondary);
        }

        .spinner {
          width: 28px;
          height: 28px;
          border: 3px solid var(--border-default);
          border-top-color: var(--accent-blue);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }

        .error-state p {
          color: var(--accent-red);
          margin: 0;
        }

        .error-state button {
          padding: 10px 20px;
          background: var(--bg-surface);
          border: 1px solid var(--border-default);
          border-radius: var(--radius-md);
          color: var(--text-primary);
          cursor: pointer;
        }

        /* Responsive */
        @media (max-width: 900px) {
          .content-grid {
            grid-template-columns: 1fr;
          }

          .sidebar {
            position: static;
            height: auto;
            border-top: 1px solid var(--border-subtle);
          }

          .main-content {
            border-right: none;
          }
        }
      `}</style>
    </div>
  );
}
