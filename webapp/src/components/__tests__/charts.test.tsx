/**
 * Minimal tests for chart components
 */

import { render, screen } from "@testing-library/react";
import { MetricCard, DonutChart, TrendingList } from "../charts";
import type { ThemeTrendResponse } from "@/lib/types";

describe("MetricCard", () => {
  it("renders with value", () => {
    render(<MetricCard label="Total Stories" value={42} />);
    expect(screen.getByText("Total Stories")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
  });

  it("renders with delta indicator", () => {
    render(<MetricCard label="Count" value={10} delta={5} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("+5")).toBeInTheDocument();
  });

  it("renders zero value", () => {
    render(<MetricCard label="Empty" value={0} />);
    expect(screen.getByText("0")).toBeInTheDocument();
  });
});

describe("DonutChart", () => {
  it("renders with data", () => {
    const data = [
      { label: "Category A", value: 10, color: "red" },
      { label: "Category B", value: 20, color: "blue" },
    ];
    render(<DonutChart data={data} />);
    expect(screen.getByText("Category A")).toBeInTheDocument();
    expect(screen.getByText("Category B")).toBeInTheDocument();
  });

  it("renders empty data without crashing", () => {
    render(<DonutChart data={[]} />);
    // Should render without crashing
    expect(document.body).toBeInTheDocument();
  });
});

describe("TrendingList", () => {
  const mockThemes: ThemeTrendResponse[] = [
    {
      theme_signature: "billing_issue",
      product_area: "billing",
      occurrence_count: 10,
      previous_count: 5,
      trend_direction: "rising",
      change_percentage: 100,
      first_seen_at: "2024-01-01",
      last_seen_at: "2024-01-15",
    },
    {
      theme_signature: "login_error",
      product_area: "auth",
      occurrence_count: 5,
      previous_count: 8,
      trend_direction: "declining",
      change_percentage: -37.5,
      first_seen_at: "2024-01-01",
      last_seen_at: "2024-01-15",
    },
  ];

  it("renders with themes", () => {
    render(<TrendingList themes={mockThemes} />);
    expect(screen.getByText(/billing_issue/)).toBeInTheDocument();
    expect(screen.getByText(/login_error/)).toBeInTheDocument();
  });

  it("renders empty state", () => {
    render(<TrendingList themes={[]} />);
    expect(screen.getByText(/No trending themes/i)).toBeInTheDocument();
  });
});
