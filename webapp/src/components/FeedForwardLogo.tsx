"use client";

import { useTheme } from "@/components/ThemeProvider";

interface FeedForwardLogoProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function FeedForwardLogo({
  size = "md",
  className = "",
}: FeedForwardLogoProps) {
  const { resolvedTheme } = useTheme();

  // Use resolved theme (already handles "system" -> actual value)
  const isDark = resolvedTheme === "dark";
  const logoSrc = isDark
    ? "/feedforward-logo-dark.png"
    : "/feedforward-logo.png";

  const heights = {
    sm: 24,
    md: 32,
    lg: 48,
  };

  const height = heights[size];

  return (
    <div className={className}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={logoSrc}
        alt="FeedForward"
        height={height}
        style={{ height: `${height}px`, width: "auto" }}
      />
    </div>
  );
}
