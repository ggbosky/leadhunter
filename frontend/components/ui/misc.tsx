import * as React from "react";
import { cn } from "@/lib/utils";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />;
}

export function Progress({ value, className, tone }: { value: number | null | undefined; className?: string; tone?: string }) {
  const v = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}>
      <div className={cn("h-full rounded-full transition-all", tone ?? "bg-primary")} style={{ width: `${v}%` }} />
    </div>
  );
}

export function Separator({ className }: { className?: string }) {
  return <div className={cn("h-px w-full bg-border", className)} />;
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed p-10 text-center">
      <p className="font-medium">{title}</p>
      {description && <p className="max-w-md text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  );
}

export function Table({ className, ...props }: React.HTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto scrollbar-thin">
      <table className={cn("w-full caption-bottom text-sm", className)} {...props} />
    </div>
  );
}
export const THead = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <thead {...p} className={cn("[&_tr]:border-b", p.className)} />;
export const TBody = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <tbody {...p} className={cn("[&_tr:last-child]:border-0", p.className)} />;
export const TR = (p: React.HTMLAttributes<HTMLTableRowElement>) => (
  <tr {...p} className={cn("border-b transition-colors hover:bg-muted/50", p.className)} />
);
export const TH = (p: React.ThHTMLAttributes<HTMLTableCellElement>) => (
  <th {...p} className={cn("h-9 px-3 text-left align-middle text-xs font-medium text-muted-foreground whitespace-nowrap", p.className)} />
);
export const TD = (p: React.TdHTMLAttributes<HTMLTableCellElement>) => <td {...p} className={cn("px-3 py-2 align-middle", p.className)} />;
