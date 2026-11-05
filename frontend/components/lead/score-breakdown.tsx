"use client";
import { useState } from "react";
import { ChevronDown, ChevronRight, Info, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { CategoryBadge, ScoreBar, ScoreRing } from "@/components/score";
import { fmtCzk } from "@/lib/format";
import type { Score } from "@/lib/types";

const ORDER: [string, string][] = [
  ["design_gap", "Design Gap"],
  ["commercial_potential", "Commercial Potential"],
  ["buying_readiness", "Buying Readiness"],
  ["service_fit", "Service Fit"],
  ["contactability", "Contactability"],
];

const BASIS: Record<string, string> = {
  visual: "vizuální AI analýza",
  technical: "pouze technické metriky (audit neúplný)",
  no_website: "firma nemá web",
  none: "web zatím neanalyzován",
};

export function ScoreBreakdown({ score, compact = false }: { score: Score | null; compact?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!score) return <p className="text-sm text-muted-foreground">Lead zatím nebyl ohodnocen – spusťte analýzu webu.</p>;
  const weights = score.components.weights ?? {};
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-4">
        <ScoreRing value={score.opportunity_score} size={compact ? 64 : 80} label="Opportunity Score" />
        <div className="space-y-1">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Opportunity Score</p>
          <CategoryBadge category={score.category} label={score.category_label} />
          <p className="text-xs text-muted-foreground">
            Confidence {score.confidence_score !== null ? Math.round(score.confidence_score) : "—"} / 100
            {score.components.known_weight_share !== undefined && ` · známo ${Math.round((score.components.known_weight_share ?? 0) * 100)} % vah`}
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {ORDER.map(([k, label]) => {
          const c = score.components[k];
          if (!c) return null;
          const isOpen = open === k;
          return (
            <div key={k}>
              <button className="w-full text-left cursor-pointer" onClick={() => setOpen(isOpen ? null : k)}>
                <ScoreBar label={label} value={c.score} confidence={c.confidence} weight={weights[k]} />
                <span className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                  {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                  {c.reasons[0] ?? "Bez důvodů"}
                </span>
              </button>
              {isOpen && (
                <div className="mt-2 space-y-2 rounded-lg border bg-muted/40 p-3 text-xs">
                  {c.note && (
                    <p className="flex gap-1 text-muted-foreground">
                      <Info className="h-3.5 w-3.5 shrink-0" /> {c.note}
                    </p>
                  )}
                  <ul className="list-disc space-y-0.5 pl-4">
                    {c.reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                  {k === "design_gap" && score.components.business_quality && (
                    <div className="space-y-1 border-t pt-2">
                      <p className="font-medium">Kvalita podnikání (Business Quality Signals)</p>
                      {score.components.business_quality.factors.map((f, i) => (
                        <div key={i} className="flex justify-between gap-2">
                          <span className="text-muted-foreground">{f.label}{f.evidence ? ` – ${f.evidence}` : ""}</span>
                          <span className="tabular-nums">{f.known ? Math.round(f.value ?? 0) : "neznámé"}</span>
                        </div>
                      ))}
                      <p className="text-muted-foreground">Kvalita webu: {score.website_quality !== null ? Math.round(score.website_quality) : "neznámá"} ({BASIS[score.website_quality_basis ?? "none"]})</p>
                    </div>
                  )}
                  {c.factors.length > 0 && k !== "design_gap" && (
                    <div className="space-y-1 border-t pt-2">
                      {c.factors.map((f, i) => (
                        <div key={i} className="flex justify-between gap-2">
                          <span className="text-muted-foreground">{f.label}{f.evidence ? ` – ${f.evidence}` : ""}</span>
                          <span className="tabular-nums">{f.known ? Math.round(f.value ?? 0) : "neznámé"}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {!compact && score.estimated_budget && (
        <div className="rounded-lg border p-3 text-sm">
          <p className="text-xs uppercase tracking-wide text-muted-foreground">Doporučená nabídka</p>
          <p className="mt-1 font-medium">{score.estimated_budget.label}</p>
          <p className="text-muted-foreground">
            {fmtCzk(score.estimated_budget.min)} – {score.estimated_budget.max ? fmtCzk(score.estimated_budget.max) : "více"}
          </p>
          <p className="mt-1 text-[11px] text-muted-foreground">{score.estimated_budget.note}</p>
        </div>
      )}

      {score.disqualification_reasons.length > 0 && (
        <div className="space-y-1">
          {score.disqualification_reasons.map((d) => (
            <div key={d.code} className="flex items-start gap-2 rounded-md bg-red-50 p-2 text-xs text-red-800 dark:bg-red-950/30 dark:text-red-300">
              <ShieldAlert className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span>
                <b>{d.label}</b> – {d.detail}
              </span>
            </div>
          ))}
        </div>
      )}
      {!compact && (
        <p className="text-[11px] text-muted-foreground">
          Algoritmus v{score.algorithm_version}. Neznámé hodnoty se nepočítají jako nula – váhy se přepočítají jen na známé komponenty.
          <Badge variant="muted" className="ml-1">transparentní scoring</Badge>
        </p>
      )}
    </div>
  );
}
