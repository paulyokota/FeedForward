"use client";

import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import type {
  StoryMetricsResponse,
  ThemeTrendResponse,
  SourceDistributionResponse,
  SyncMetricsResponse,
  StatusKey,
} from "@/lib/types";
import { STATUS_CONFIG, PRIORITY_CONFIG } from "@/lib/types";
import { MetricCard } from "@/components/charts/MetricCard";
import { DonutChart } from "@/components/charts/DonutChart";
import { TrendingList } from "@/components/charts/TrendingList";
import { ThemeToggle } from "@/components/ThemeToggle";
import { FeedForwardLogo } from "@/components/FeedForwardLogo";
import Link from "next/link";

type PeriodDays = 7 | 30 | 90;

export default function AnalyticsPage() {
  const [metrics, setMetrics] = useState<StoryMetricsResponse | null>(null);
  const [sources, setSources] = useState<SourceDistributionResponse[]>([]);
  const [syncMetrics, setSyncMetrics] = useState<SyncMetricsResponse | null>(
    null,
  );
  const [trending, setTrending] = useState<ThemeTrendResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [period, setPeriod] = useState<PeriodDays>(7);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const fetchData = useCallback(
    async (showRefreshing = false) => {
      if (showRefreshing) {
        setIsRefreshing(true);
      }

      try {
        const [metricsData, sourcesData, syncData, trendingData] =
          await Promise.all([
            api.analytics.getStoryMetrics(),
            api.analytics.getSourceDistribution(),
            api.analytics.getSyncMetrics(),
            api.analytics.getTrendingThemes(period, 20),
          ]);

        setMetrics(metricsData);
        setSources(sourcesData);
        setSyncMetrics(syncData);
        setTrending(trendingData);
        setError(null);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to load analytics",
        );
      } finally {
        setLoading(false);
        setIsRefreshing(false);
      }
    },
    [period],
  );

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleRefresh = () => {
    fetchData(true);
  };

  // Transform status data for DonutChart
  const statusChartData = metrics
    ? Object.entries(metrics.by_status).map(([status, count]) => ({
        label: STATUS_CONFIG[status as StatusKey]?.label || status,
        value: count,
        color: STATUS_CONFIG[status as StatusKey]?.color || "var(--text-muted)",
      }))
    : [];

  // Transform priority data for DonutChart
  const priorityChartData = metrics
    ? Object.entries(metrics.by_priority)
        .filter(([_, count]) => count > 0)
        .map(([priority, count]) => ({
          label: PRIORITY_CONFIG[priority]?.label || priority || "None",
          value: count,
          color: PRIORITY_CONFIG[priority]?.color || "var(--text-muted)",
        }))
    : [];

  // Transform source data for DonutChart
  const sourceChartData = sources.map((source) => ({
    label: source.source,
    value: source.story_count,
    color:
      source.source.toLowerCase() === "intercom"
        ? "var(--accent-teal)"
        : "var(--accent-purple)",
  }));

  if (loading) {
    return (
      <div className="loading-container loading-delayed">
        <div className="loading-spinner" />
        <span>Loading analytics...</span>
        <style jsx>{`
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
        `}</style>
      </div>
    );
  }

  if (error) {
    return (
      <div className="error-container">
        <p>Error: {error}</p>
        <button onClick={() => fetchData()}>Retry</button>
        <style jsx>{`
          .error-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            gap: 20px;
            color: var(--text-secondary);
          }

          .error-container p {
            font-size: 15px;
            color: var(--accent-red);
          }

          .error-container button {
            padding: 10px 20px;
            background: var(--bg-surface);
            border: none;
            border-radius: var(--radius-md);
            color: var(--text-primary);
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
            box-shadow: var(--shadow-sm);
          }

          .error-container button:hover {
            background: var(--bg-elevated);
            box-shadow: var(--shadow-md);
          }
        `}</style>
      </div>
    );
  }

  return (
    <div className="analytics-layout">
      <header className="analytics-header">
        <div className="header-left">
          <Link href="/" className="logo-link">
            <FeedForwardLogo size="sm" />
          </Link>
          <div className="header-divider" />
          <span className="page-subtitle">Analytics</span>
        </div>

        <div className="header-center">
          <div className="period-selector">
            {([7, 30, 90] as PeriodDays[]).map((days) => (
              <button
                key={days}
                className={`period-btn ${period === days ? "active" : ""}`}
                onClick={() => setPeriod(days)}
              >
                {days}d
              </button>
            ))}
          </div>
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
              <rect x="3" y="3" width="7" height="7" />
              <rect x="14" y="3" width="7" height="7" />
              <rect x="14" y="14" width="7" height="7" />
              <rect x="3" y="14" width="7" height="7" />
            </svg>
            Board
          </Link>
          <Link href="/tools/extraction" className="nav-link">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
            </svg>
            Tools
          </Link>
          <ThemeToggle />
          <button
            className="btn-secondary"
            onClick={handleRefresh}
            disabled={isRefreshing}
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              className={isRefreshing ? "spin" : ""}
            >
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38" />
            </svg>
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      <main className="analytics-content stagger-children">
        {/* Metrics Row */}
        <section className="metrics-row">
          <MetricCard
            label="Total Stories"
            value={metrics?.total_stories ?? 0}
            icon={
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            }
          />
          <MetricCard
            label="Created (7d)"
            value={metrics?.created_last_7_days ?? 0}
            icon={
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            }
          />
          <MetricCard
            label="Created (30d)"
            value={metrics?.created_last_30_days ?? 0}
            icon={
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
            }
          />
          <MetricCard
            label="Avg Confidence"
            value={
              metrics?.avg_confidence_score !== null
                ? `${Math.round((metrics?.avg_confidence_score ?? 0) * 100)}%`
                : "N/A"
            }
            icon={
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              </svg>
            }
          />
        </section>

        {/* Charts Row 1: Status + Priority */}
        <section className="charts-row">
          <div className="chart-card">
            <h3 className="chart-title">Status Distribution</h3>
            <div className="chart-content">
              {statusChartData.length > 0 ? (
                <DonutChart
                  data={statusChartData}
                  size={140}
                  strokeWidth={18}
                />
              ) : (
                <div className="empty-chart">No data</div>
              )}
            </div>
          </div>

          <div className="chart-card">
            <h3 className="chart-title">Priority Distribution</h3>
            <div className="chart-content">
              {priorityChartData.length > 0 ? (
                <DonutChart
                  data={priorityChartData}
                  size={140}
                  strokeWidth={18}
                />
              ) : (
                <div className="empty-chart">No priority data</div>
              )}
            </div>
          </div>
        </section>

        {/* Charts Row 2: Source + Sync */}
        <section className="charts-row">
          <div className="chart-card">
            <h3 className="chart-title">Source Distribution</h3>
            <div className="chart-content">
              {sourceChartData.length > 0 ? (
                <DonutChart
                  data={sourceChartData}
                  size={140}
                  strokeWidth={18}
                />
              ) : (
                <div className="empty-chart">No source data</div>
              )}
            </div>
          </div>

          <div className="chart-card">
            <h3 className="chart-title">Sync Metrics</h3>
            <div className="sync-grid">
              <div className="sync-metric">
                <span className="sync-value">
                  {syncMetrics?.total_synced ?? 0}
                </span>
                <span className="sync-label">Total Synced</span>
              </div>
              <div className="sync-metric">
                <span className="sync-value">
                  {syncMetrics?.unsynced_count ?? 0}
                </span>
                <span className="sync-label">Unsynced</span>
              </div>
              <div className="sync-metric">
                <span className="sync-value">
                  {syncMetrics?.push_count ?? 0}
                </span>
                <span className="sync-label">Push Count</span>
              </div>
              <div className="sync-metric">
                <span className="sync-value">
                  {syncMetrics?.pull_count ?? 0}
                </span>
                <span className="sync-label">Pull Count</span>
              </div>
            </div>
          </div>
        </section>

        {/* Trending Themes */}
        <section className="trending-section">
          <div className="trending-card">
            <div className="trending-header">
              <h3 className="chart-title">Trending Themes</h3>
              <span className="period-badge">{period} days</span>
            </div>
            <TrendingList themes={trending} maxItems={15} />
          </div>
        </section>
      </main>

      <style jsx>{`
        .analytics-layout {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }

        .analytics-header {
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
          gap: 20px;
        }

        :global([data-theme="light"]) .analytics-header {
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
          flex-shrink: 0;
        }

        .logo-link {
          display: flex;
          align-items: center;
        }

        .header-divider {
          width: 1px;
          height: 24px;
          background: var(--border-default);
        }

        .page-subtitle {
          font-size: 16px;
          font-weight: 500;
          color: var(--text-secondary);
        }

        .header-center {
          flex: 1;
          display: flex;
          justify-content: center;
        }

        .period-selector {
          display: flex;
          align-items: center;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 32%),
            hsl(0, 0%, 28%)
          );
          border-radius: var(--radius-full);
          padding: 4px;
          gap: 2px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .period-selector {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 96%),
            hsl(0, 0%, 90%)
          );
          box-shadow: var(--shadow-inset);
        }

        .period-btn {
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 8px 16px;
          border: none;
          background: transparent;
          border-radius: var(--radius-full);
          color: var(--text-tertiary);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
        }

        .period-btn:hover {
          color: var(--text-secondary);
          background: var(--bg-hover);
        }

        .period-btn.active {
          background: var(--bg-surface);
          color: var(--text-primary);
          box-shadow: var(--shadow-sm);
        }

        .header-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-shrink: 0;
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

        .btn-secondary {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 8px 18px;
          border-radius: var(--radius-full);
          font-size: 13px;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.2s ease;
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 32%),
            hsl(0, 0%, 28%)
          );
          border: none;
          color: var(--text-secondary);
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .btn-secondary {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 96%),
            hsl(0, 0%, 90%)
          );
        }

        .btn-secondary:hover {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 38%),
            hsl(0, 0%, 32%)
          );
          color: var(--text-primary);
          box-shadow: var(--shadow-md);
        }

        :global([data-theme="light"]) .btn-secondary:hover {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 94%)
          );
        }

        .btn-secondary:disabled {
          opacity: 0.7;
          cursor: not-allowed;
        }

        .btn-secondary :global(.spin) {
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }

        .analytics-content {
          flex: 1;
          padding: 24px 28px;
          display: flex;
          flex-direction: column;
          gap: 24px;
          max-width: 1200px;
          margin: 0 auto;
          width: 100%;
        }

        .metrics-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 16px;
        }

        .charts-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
          gap: 16px;
        }

        .chart-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border-radius: var(--radius-lg);
          padding: 20px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .chart-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .chart-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 16px 0;
        }

        .chart-content {
          display: flex;
          justify-content: center;
          align-items: center;
          min-height: 180px;
        }

        .empty-chart {
          color: var(--text-tertiary);
          font-size: 13px;
        }

        .sync-grid {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 16px;
          padding: 8px 0;
        }

        .sync-metric {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 4px;
          padding: 12px;
          background: var(--bg-elevated);
          border-radius: var(--radius-md);
        }

        :global([data-theme="light"]) .sync-metric {
          background: var(--bg-hover);
        }

        .sync-value {
          font-size: 24px;
          font-weight: 600;
          color: var(--text-primary);
          font-variant-numeric: tabular-nums;
        }

        .sync-label {
          font-size: 11px;
          font-weight: 500;
          color: var(--text-tertiary);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        .trending-section {
          width: 100%;
        }

        .trending-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 16%),
            hsl(0, 0%, 12%)
          );
          border-radius: var(--radius-lg);
          padding: 20px;
          box-shadow: var(--shadow-sm);
        }

        :global([data-theme="light"]) .trending-card {
          background: linear-gradient(
            to bottom,
            hsl(0, 0%, 100%),
            hsl(0, 0%, 97%)
          );
        }

        .trending-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 16px;
        }

        .period-badge {
          font-size: 11px;
          font-weight: 500;
          color: var(--text-tertiary);
          background: var(--bg-elevated);
          padding: 4px 10px;
          border-radius: var(--radius-full);
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }

        :global([data-theme="light"]) .period-badge {
          background: var(--bg-hover);
        }

        /* Responsive adjustments */
        @media (max-width: 768px) {
          .analytics-header {
            flex-wrap: wrap;
            gap: 12px;
            padding: 12px 16px;
            margin: 12px 16px 0;
          }

          .header-center {
            order: 3;
            flex-basis: 100%;
            justify-content: center;
          }

          .analytics-content {
            padding: 16px;
          }

          .metrics-row {
            grid-template-columns: 1fr 1fr;
          }

          .charts-row {
            grid-template-columns: 1fr;
          }
        }

        @media (max-width: 480px) {
          .metrics-row {
            grid-template-columns: 1fr;
          }

          .header-left {
            gap: 10px;
          }

          .page-subtitle {
            font-size: 14px;
          }
        }
      `}</style>
    </div>
  );
}
