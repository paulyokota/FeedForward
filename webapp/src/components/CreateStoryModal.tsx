"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { Story, StatusKey, PriorityKey } from "@/lib/types";
import { STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/types";

interface CreateStoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (story: Story) => void;
}

export function CreateStoryModal({
  isOpen,
  onClose,
  onCreated,
}: CreateStoryModalProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<StatusKey>("candidate");
  const [priority, setPriority] = useState<PriorityKey | "">("");
  const [productArea, setProductArea] = useState("");
  const [labels, setLabels] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("Title is required");
      return;
    }

    setIsSubmitting(true);
    setError(null);

    try {
      const story = await api.stories.create({
        title: title.trim(),
        description: description.trim() || null,
        status,
        priority: priority === "" ? null : priority,
        product_area: productArea.trim() || null,
        labels: labels
          .split(",")
          .map((l) => l.trim())
          .filter(Boolean),
      });
      onCreated(story);
      handleClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create story");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    setTitle("");
    setDescription("");
    setStatus("candidate");
    setPriority("");
    setProductArea("");
    setLabels("");
    setError(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create New Story</h2>
          <button className="close-btn" onClick={handleClose}>
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          {error && <div className="error-message">{error}</div>}

          <div className="form-group">
            <label htmlFor="title">Title *</label>
            <input
              id="title"
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What needs to be done?"
              autoFocus
            />
          </div>

          <div className="form-group">
            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Describe the story in more detail..."
              rows={4}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label htmlFor="status">Status</label>
              <select
                id="status"
                value={status}
                onChange={(e) => setStatus(e.target.value as StatusKey)}
              >
                {Object.entries(STATUS_CONFIG).map(([key, config]) => (
                  <option key={key} value={key}>
                    {config.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="priority">Priority</label>
              <select
                id="priority"
                value={priority}
                onChange={(e) =>
                  setPriority(e.target.value as PriorityKey | "")
                }
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

          <div className="form-group">
            <label htmlFor="productArea">Product Area</label>
            <input
              id="productArea"
              type="text"
              value={productArea}
              onChange={(e) => setProductArea(e.target.value)}
              placeholder="e.g., Billing, Analytics, Extension"
            />
          </div>

          <div className="form-group">
            <label htmlFor="labels">Labels</label>
            <input
              id="labels"
              type="text"
              value={labels}
              onChange={(e) => setLabels(e.target.value)}
              placeholder="Comma-separated labels"
            />
          </div>

          <div className="modal-actions">
            <button
              type="button"
              className="btn-secondary"
              onClick={handleClose}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Creating..." : "Create Story"}
            </button>
          </div>
        </form>

        <style jsx>{`
          .modal-overlay {
            position: fixed;
            inset: 0;
            background: rgba(0, 0, 0, 0.7);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 100;
            padding: 20px;
          }

          .modal-content {
            background: var(--bg-surface);
            border: 1px solid var(--border-default);
            border-radius: var(--radius-lg);
            width: 100%;
            max-width: 520px;
            max-height: 90vh;
            overflow-y: auto;
            box-shadow: var(--shadow-lg);
          }

          .modal-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-subtle);
          }

          .modal-header h2 {
            font-size: 18px;
            font-weight: 600;
            color: var(--text-primary);
            margin: 0;
          }

          .close-btn {
            background: none;
            border: none;
            color: var(--text-tertiary);
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: all 0.15s ease;
          }

          .close-btn:hover {
            color: var(--text-primary);
            background: var(--bg-hover);
          }

          form {
            padding: 24px;
          }

          .error-message {
            background: var(--accent-red-dim);
            color: var(--accent-red);
            padding: 10px 14px;
            border-radius: var(--radius-md);
            font-size: 13px;
            margin-bottom: 16px;
          }

          .form-group {
            margin-bottom: 18px;
          }

          .form-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
          }

          label {
            display: block;
            font-size: 13px;
            font-weight: 500;
            color: var(--text-secondary);
            margin-bottom: 6px;
          }

          input,
          textarea,
          select {
            width: 100%;
            padding: 10px 12px;
            background: var(--bg-elevated);
            border: 1px solid var(--border-default);
            border-radius: var(--radius-md);
            color: var(--text-primary);
            font-size: 14px;
            font-family: inherit;
            transition: border-color 0.15s ease;
          }

          input:focus,
          textarea:focus,
          select:focus {
            outline: none;
            border-color: var(--accent-blue);
          }

          input::placeholder,
          textarea::placeholder {
            color: var(--text-muted);
          }

          select {
            cursor: pointer;
          }

          textarea {
            resize: vertical;
            min-height: 80px;
          }

          .modal-actions {
            display: flex;
            justify-content: flex-end;
            gap: 10px;
            margin-top: 24px;
            padding-top: 20px;
            border-top: 1px solid var(--border-subtle);
          }

          .btn-secondary,
          .btn-primary {
            padding: 10px 18px;
            border-radius: var(--radius-md);
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.15s ease;
          }

          .btn-secondary {
            background: var(--bg-elevated);
            border: 1px solid var(--border-default);
            color: var(--text-secondary);
          }

          .btn-secondary:hover {
            background: var(--bg-hover);
            color: var(--text-primary);
          }

          .btn-primary {
            background: var(--accent-blue);
            border: 1px solid var(--accent-blue);
            color: white;
          }

          .btn-primary:hover:not(:disabled) {
            background: #74b3ff;
            border-color: #74b3ff;
          }

          .btn-primary:disabled {
            opacity: 0.6;
            cursor: not-allowed;
          }
        `}</style>
      </div>
    </div>
  );
}
