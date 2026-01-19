"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import { ThemeToggle } from "@/components/ThemeToggle";

interface ExtractionStatus {
  status: "idle" | "running" | "paused" | "completed" | "error";
  isRunning: boolean;
  error: string | null;
  output: string[];
  manifest: {
    extraction?: {
      timestamp?: string;
      doc_name?: string;
    };
    content?: {
      pages?: {
        total: number;
        extracted: number;
        with_content: number;
      };
    };
    costs?: {
      usdTotal: number;
      inputTokens: number;
      outputTokens: number;
      imageCount: number;
    };
  } | null;
  logTail: string[];
  costs: {
    usdTotal: number;
    inputTokens: number;
    outputTokens: number;
    imageCount: number;
  } | null;
  runningCost: number;
  mode: "dom" | "vision";
}

export default function ExtractionPage() {
  const [status, setStatus] = useState<ExtractionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [extractionMode, setExtractionMode] = useState<"dom" | "vision">(
    "vision",
  );

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/extraction");
      if (!response.ok) throw new Error("Failed to fetch status");
      const data = await response.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Auto-refresh when running
  useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(fetchStatus, 2000);
    return () => clearInterval(interval);
  }, [autoRefresh, fetchStatus]);

  const handleAction = async (action: "start" | "stop" | "clear") => {
    setActionLoading(true);
    try {
      const response = await fetch("/api/extraction", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, mode: extractionMode }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.error || "Action failed");
      } else {
        await fetchStatus();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setActionLoading(false);
    }
  };

  const getStatusColor = () => {
    switch (status?.status) {
      case "running":
        return "var(--accent-blue)";
      case "completed":
        return "var(--accent-green)";
      case "error":
        return "var(--accent-red)";
      default:
        return "var(--text-muted)";
    }
  };

  const getStatusLabel = () => {
    switch (status?.status) {
      case "running":
        return "Running";
      case "completed":
        return "Completed";
      case "error":
        return "Error";
      case "paused":
        return "Paused";
      default:
        return "Idle";
    }
  };

  if (loading) {
    return (
      <div className="loading-container">
        <div className="loading-spinner" />
        <span>Loading extraction status...</span>
      </div>
    );
  }

  return (
    <div className="extraction-layout">
      <header className="extraction-header">
        <div className="header-left">
          <Link href="/" className="logo-link">
            <FeedForwardLogo size="sm" />
          </Link>
          <div className="header-divider" />
          <span className="page-subtitle">Tools</span>
          <span className="page-title">Coda Extraction</span>
        </div>
        <div className="header-actions">
          <Link href="/" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
              <polyline points="9 22 9 12 15 12 15 22" />
            </svg>
            Stories
          </Link>
          <Link href="/analytics" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M18 20V10" />
              <path d="M12 20V4" />
              <path d="M6 20v-6" />
            </svg>
            Analytics
          </Link>
          <ThemeToggle />
        </div>
      </header>

      <main className="extraction-main">
        <div className="controls-panel">
          <div className="status-section">
            <div className="status-indicator">
              <span
                className="status-dot"
                style={{ backgroundColor: getStatusColor() }}
              />
              <span className="status-label">{getStatusLabel()}</span>
              {status?.isRunning && <span className="status-pulse" />}
            </div>

            {status?.error && (
              <div className="error-banner">
                <svg
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                {status.error}
              </div>
            )}
          </div>

          <div className="mode-selector">
            <h3>Extraction Mode</h3>
            <div className="mode-options">
              <label
                className={`mode-option ${extractionMode === "vision" ? "active" : ""}`}
              >
                <input
                  type="radio"
                  name="mode"
                  value="vision"
                  checked={extractionMode === "vision"}
                  onChange={() => setExtractionMode("vision")}
                  disabled={status?.isRunning}
                />
                <div className="mode-content">
                  <span className="mode-name">Vision (GPT-4o)</span>
                  <span className="mode-desc">
                    Screenshot + AI extraction - better for canvas content
                  </span>
                  <span className="mode-cost">~$0.01/page</span>
                </div>
              </label>
              <label
                className={`mode-option ${extractionMode === "dom" ? "active" : ""}`}
              >
                <input
                  type="radio"
                  name="mode"
                  value="dom"
                  checked={extractionMode === "dom"}
                  onChange={() => setExtractionMode("dom")}
                  disabled={status?.isRunning}
                />
                <div className="mode-content">
                  <span className="mode-name">DOM Parser</span>
                  <span className="mode-desc">
                    Direct HTML extraction - free but limited
                  </span>
                  <span className="mode-cost">Free</span>
                </div>
              </label>
            </div>
          </div>

          <div className="action-buttons">
            <button
              className="btn-primary"
              onClick={() => handleAction("start")}
              disabled={actionLoading || status?.isRunning}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              Start Extraction
            </button>

            <button
              className="btn-danger"
              onClick={() => handleAction("stop")}
              disabled={actionLoading || !status?.isRunning}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <rect x="6" y="6" width="12" height="12" />
              </svg>
              Stop
            </button>

            <button
              className="btn-secondary"
              onClick={() => handleAction("clear")}
              disabled={actionLoading}
            >
              Clear Output
            </button>

            <label className="auto-refresh">
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              Auto-refresh
            </label>
          </div>

          {status?.manifest && (
            <div className="manifest-section">
              <h3>Extraction Progress</h3>
              <div className="manifest-stats">
                <div className="stat">
                  <span className="stat-value">
                    {status.manifest.content?.pages?.extracted || 0}
                  </span>
                  <span className="stat-label">Pages Extracted</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {status.manifest.content?.pages?.with_content || 0}
                  </span>
                  <span className="stat-label">With Content</span>
                </div>
                <div className="stat">
                  <span className="stat-value">
                    {status.manifest.content?.pages?.total || 0}
                  </span>
                  <span className="stat-label">Total Discovered</span>
                </div>
              </div>
              {status.manifest.extraction?.timestamp && (
                <div className="manifest-meta">
                  Last updated:{" "}
                  {new Date(
                    status.manifest.extraction.timestamp,
                  ).toLocaleString()}
                </div>
              )}
            </div>
          )}

          {((status?.runningCost ?? 0) > 0 || status?.costs) && (
            <div className="cost-section">
              <h3>Cost Tracking</h3>
              <div className="cost-display">
                <div className="cost-current">
                  <span className="cost-label">Running Cost</span>
                  <span className="cost-value">
                    $
                    {(
                      status?.runningCost ||
                      status?.costs?.usdTotal ||
                      0
                    ).toFixed(4)}
                  </span>
                </div>
                {status?.costs && (
                  <div className="cost-details">
                    <div className="cost-detail">
                      <span>Images:</span>
                      <span>{status.costs.imageCount}</span>
                    </div>
                    <div className="cost-detail">
                      <span>Input tokens:</span>
                      <span>{status.costs.inputTokens?.toLocaleString()}</span>
                    </div>
                    <div className="cost-detail">
                      <span>Output tokens:</span>
                      <span>{status.costs.outputTokens?.toLocaleString()}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="instructions">
            <h3>Instructions</h3>
            <ol>
              <li>Click "Start Extraction" to launch the Playwright browser</li>
              <li>
                A Chromium window will open - log into Coda with your Google
                account
              </li>
              <li>
                Once logged in, the script will automatically start extracting
                pages
              </li>
              <li>Monitor progress in the output panel below</li>
              <li>
                Extraction is resumable - if stopped, click Start again to
                continue
              </li>
            </ol>
            <p className="note">
              Note: The browser window must stay open during extraction. Pages
              are saved to <code>data/coda_raw/pages/</code>
            </p>
          </div>
        </div>

        <div className="output-panel">
          <div className="output-header">
            <h3>Output Log</h3>
            <span className="output-count">
              {status?.output?.length || 0} lines
            </span>
          </div>
          <div className="output-content">
            {status?.output && status.output.length > 0 ? (
              status.output.map((line, i) => (
                <div
                  key={i}
                  className={`output-line ${line.includes("[ERROR]") ? "error" : ""} ${line.includes("✓") ? "success" : ""} ${line.includes("⚠") ? "warning" : ""}`}
                >
                  {line}
                </div>
              ))
            ) : (
              <div className="output-empty">
                No output yet. Start extraction to see progress.
              </div>
            )}
          </div>
        </div>
      </main>

      {error && (
        <div className="toast-error">
          {error}
          <button onClick={() => setError(null)}>×</button>
        </div>
      )}

      <style jsx>{`
        .extraction-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          background: var(--bg-void);
        }

        .extraction-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 12px 24px;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 22%),
            hsl(0, 0%, 18%)
          );
          box-shadow: var(--shadow-md);
          position: sticky;
          top: 16px;
          margin: 16px 24px 0;
          border-radius: var(--radius-full);
          z-index: 10;
        }

        :global([data-theme="light"]) .extraction-header {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 94%)
          );
        }

        .header-left {
          display: flex;
          align-items: center;
          gap: 14px;
        }

        .logo-link {
          display: flex;
          text-decoration: none;
        }

        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }

        .page-subtitle {
          font-size: 14px;
          color: var(--text-muted);
        }

        .page-title {
          font-size: 16px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .header-actions :global(.nav-link) {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 8px 14px;
          border-radius: var(--radius-full);
          font-size: 13px;
          font-weight: 500;
          color: var(--text-secondary);
          text-decoration: none;
          transition: all 0.15s ease;
        }

        .header-actions :global(.nav-link):hover {
          color: var(--text-primary);
          background: var(--bg-hover);
        }

        .extraction-main {
          flex: 1;
          display: grid;
          grid-template-columns: 400px 1fr;
          gap: 24px;
          padding: 24px;
        }

        .controls-panel {
          display: flex;
          flex-direction: column;
          gap: 20px;
        }

        .status-section {
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          padding: 20px;
        }

        .status-indicator {
          display: flex;
          align-items: center;
          gap: 10px;
        }

        .status-dot {
          width: 12px;
          height: 12px;
          border-radius: 50%;
        }

        .status-label {
          font-size: 18px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .status-pulse {
          width: 8px;
          height: 8px;
          background: var(--accent-blue);
          border-radius: 50%;
          animation: pulse 1.5s ease-in-out infinite;
        }

        @keyframes pulse {
          0%,
          100% {
            opacity: 1;
            transform: scale(1);
          }
          50% {
            opacity: 0.5;
            transform: scale(1.5);
          }
        }

        .error-banner {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 12px;
          padding: 10px 14px;
          background: rgba(255, 107, 107, 0.1);
          border-radius: var(--radius-md);
          color: var(--accent-red);
          font-size: 13px;
        }

        .action-buttons {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          padding: 20px;
        }

        .btn-primary,
        .btn-secondary,
        .btn-danger {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 10px 18px;
          border-radius: var(--radius-md);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          border: none;
        }

        .btn-primary {
          background: var(--accent-blue);
          color: white;
        }

        .btn-primary:hover:not(:disabled) {
          background: #74b3ff;
        }

        .btn-primary:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .btn-danger {
          background: var(--accent-red);
          color: white;
        }

        .btn-danger:hover:not(:disabled) {
          background: #ff8585;
        }

        .btn-danger:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .btn-secondary {
          background: var(--bg-elevated);
          color: var(--text-secondary);
        }

        .btn-secondary:hover:not(:disabled) {
          background: var(--bg-hover);
          color: var(--text-primary);
        }

        .auto-refresh {
          display: flex;
          align-items: center;
          gap: 6px;
          font-size: 13px;
          color: var(--text-secondary);
          cursor: pointer;
          margin-left: auto;
        }

        .auto-refresh input {
          cursor: pointer;
        }

        .manifest-section {
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          padding: 20px;
        }

        .manifest-section h3 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 16px 0;
        }

        .manifest-stats {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 12px;
        }

        .stat {
          text-align: center;
          padding: 12px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
        }

        .stat-value {
          display: block;
          font-size: 24px;
          font-weight: 700;
          color: var(--text-primary);
        }

        .stat-label {
          font-size: 11px;
          color: var(--text-muted);
          text-transform: uppercase;
        }

        .manifest-meta {
          margin-top: 12px;
          font-size: 12px;
          color: var(--text-tertiary);
        }

        .mode-selector {
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          padding: 20px;
        }

        .mode-selector h3 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 12px 0;
        }

        .mode-options {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }

        .mode-option {
          display: flex;
          align-items: flex-start;
          gap: 12px;
          padding: 12px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
          cursor: pointer;
          border: 2px solid transparent;
          transition: all 0.15s ease;
        }

        .mode-option:hover {
          background: var(--bg-hover);
        }

        .mode-option.active {
          border-color: var(--accent-blue);
          background: rgba(99, 166, 255, 0.1);
        }

        .mode-option input {
          margin-top: 3px;
        }

        .mode-content {
          display: flex;
          flex-direction: column;
          gap: 2px;
        }

        .mode-name {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
        }

        .mode-desc {
          font-size: 12px;
          color: var(--text-secondary);
        }

        .mode-cost {
          font-size: 11px;
          color: var(--accent-green);
          font-weight: 500;
        }

        .cost-section {
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          padding: 20px;
        }

        .cost-section h3 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 12px 0;
        }

        .cost-display {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .cost-current {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
        }

        .cost-label {
          font-size: 13px;
          color: var(--text-secondary);
        }

        .cost-value {
          font-size: 24px;
          font-weight: 700;
          color: var(--accent-green);
        }

        .cost-details {
          display: flex;
          flex-direction: column;
          gap: 6px;
          font-size: 12px;
        }

        .cost-detail {
          display: flex;
          justify-content: space-between;
          color: var(--text-muted);
        }

        .cost-detail span:last-child {
          color: var(--text-secondary);
          font-family: var(--font-geist-mono);
        }

        .instructions {
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          padding: 20px;
        }

        .instructions h3 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 12px 0;
        }

        .instructions ol {
          margin: 0;
          padding-left: 20px;
          font-size: 13px;
          color: var(--text-secondary);
          line-height: 1.8;
        }

        .instructions .note {
          margin-top: 12px;
          padding: 10px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
          font-size: 12px;
          color: var(--text-tertiary);
        }

        .instructions code {
          background: var(--bg-void);
          padding: 2px 6px;
          border-radius: 4px;
          font-family: var(--font-geist-mono);
          font-size: 11px;
        }

        .output-panel {
          background: var(--bg-surface);
          border-radius: var(--radius-lg);
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .output-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 16px 20px;
          border-bottom: 1px solid var(--border-subtle);
        }

        .output-header h3 {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .output-count {
          font-size: 12px;
          color: var(--text-muted);
        }

        .output-content {
          flex: 1;
          overflow-y: auto;
          padding: 16px 20px;
          font-family: var(--font-geist-mono);
          font-size: 12px;
          line-height: 1.6;
          max-height: calc(100vh - 280px);
        }

        .output-line {
          color: var(--text-secondary);
          white-space: pre-wrap;
          word-break: break-word;
        }

        .output-line.error {
          color: var(--accent-red);
        }

        .output-line.success {
          color: var(--accent-green);
        }

        .output-line.warning {
          color: var(--accent-yellow);
        }

        .output-empty {
          color: var(--text-muted);
          text-align: center;
          padding: 40px;
        }

        .toast-error {
          position: fixed;
          bottom: 24px;
          right: 24px;
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px 16px;
          background: var(--accent-red);
          color: white;
          border-radius: var(--radius-md);
          font-size: 13px;
          box-shadow: var(--shadow-lg);
          z-index: 100;
        }

        .toast-error button {
          background: none;
          border: none;
          color: white;
          font-size: 18px;
          cursor: pointer;
          padding: 0;
          line-height: 1;
        }

        .loading-container {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          min-height: 100vh;
          gap: 16px;
          color: var(--text-secondary);
          font-size: 14px;
        }

        .loading-spinner {
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

        @media (max-width: 900px) {
          .extraction-main {
            grid-template-columns: 1fr;
          }

          .output-content {
            max-height: 400px;
          }
        }
      `}</style>
    </div>
  );
}
