"use client";
import { Badge } from "@/components/ui/badge";
import { CATEGORY_VARIANT, fmtScore, scoreBar, scoreTone } from "@/lib/format";
import { cn } from "@/lib/utils";

export function ScoreRing({ value, size = 64, label }: { value: number | null | undefined; size?: number; label?: string }) {
  const r = (size - 8) / 2;
  const c = 2 * Math.PI * r;
  const v = value ?? 0;
  const stroke =
    value === null || value === undefined ? "var(--color-muted-foreground)" : v >= 80 ? "#10b981" : v >= 60 ? "#0ea5e9" : v >= 40 ? "#f59e0b" : "#ef4444";
  return (
    <div className="relative inline-grid place-items-center" style={{ width: size, height: size }} title={label}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="var(--color-muted)" strokeWidth={6} fill="none" />
        {value !== null && value !== undefined && (
          <circle cx={size / 2} cy={size / 2} r={r} stroke={stroke} strokeWidth={6} fill="none" strokeLinecap="round"
            strokeDasharray={c} strokeDashoffset={c - (c * v) / 100} />
        )}
      </svg>
      <span className={cn("absolute font-bold", size >= 64 ? "text-lg" : "text-sm", scoreTone(value))}>{fmtScore(value)}</span>
    </div>
  );
}

export function ScorePill({ value, className }: { value: number | null | undefined; className?: string }) {
  return (
    <span className={cn("inline-flex min-w-9 justify-center rounded-md border px-1.5 py-0.5 text-xs font-semibold tabular-nums", scoreTone(value), className)}>
      {fmtScore(value)}
    </span>
  );
}

export function CategoryBadge({ category, label }: { category: string | null | undefined; label?: string | null }) {
  if (!category) return <Badge variant="muted">Neanalyzováno</Badge>;
  return <Badge variant={CATEGORY_VARIANT[category] ?? "muted"}>{label ?? category}</Badge>;
}

export function ScoreBar({ label, value, confidence, weight, hint }: { label: string; value: number | null | undefined; confidence?: number; weight?: number; hint?: string }) {
  return (
    <div className="space-y-1" title={hint}>
      <div className="flex items-baseline justify-between gap-2 text-xs">
        <span className="font-medium">
          {label}
          {weight !== undefined && <span className="ml-1 text-muted-foreground">({Math.round(weight * 100)} %)</span>}
        </span>
        <span className="flex items-center gap-2">
          {confidence !== undefined && value !== null && value !== undefined && (
            <span className="text-muted-foreground">jistota {Math.round(confidence * 100)} %</span>
          )}
          <span className={cn("font-semibold tabular-nums", scoreTone(value))}>{value === null || value === undefined ? "neznámé" : Math.round(value)}</span>
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        {value !== null && value !== undefined ? (
          <div className={cn("h-full rounded-full", scoreBar(value))} style={{ width: `${Math.max(2, value)}%` }} />
        ) : (
          <div className="h-full w-full bg-[repeating-linear-gradient(45deg,transparent,transparent_4px,var(--color-border)_4px,var(--color-border)_8px)]" />
        )}
      </div>
    </div>
  );
}
