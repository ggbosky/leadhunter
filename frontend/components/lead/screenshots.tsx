"use client";
import { useState } from "react";
import { Monitor, Smartphone } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type { CompanyDetail } from "@/lib/types";

const PAGE_LABELS: Record<string, string> = { home: "Úvod", services: "Služby", portfolio: "Portfolio", contact: "Kontakt" };

export function ScreenshotGallery({ audit, compact = false }: { audit: CompanyDetail["audit"]; compact?: boolean }) {
  const shots = audit?.screenshots ?? [];
  const [active, setActive] = useState(0);
  const [zoom, setZoom] = useState(false);
  if (!shots.length) {
    return (
      <div className="grid h-56 place-items-center rounded-lg border border-dashed text-sm text-muted-foreground">
        Screenshot zatím není k dispozici
      </div>
    );
  }
  const cur = shots[Math.min(active, shots.length - 1)];
  return (
    <div className="space-y-2">
      <button
        className={cn("block aspect-[16/10] w-full overflow-hidden rounded-lg border bg-muted cursor-zoom-in", compact ? "max-h-80" : "")}
        onClick={() => setZoom(true)}
        title="Zvětšit"
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={cur.fold_url ?? cur.url} alt={`${cur.page} ${cur.device}`}
          className={cn(cur.device === "mobile" ? "mx-auto h-full w-auto" : "h-full w-full object-contain object-top")} />
      </button>
      <div className="flex flex-wrap gap-1.5">
        {shots.map((s, i) => (
          <button
            key={i}
            onClick={() => setActive(i)}
            className={cn("flex items-center gap-1 rounded-md border px-2 py-1 text-xs cursor-pointer", i === active ? "border-primary bg-accent" : "hover:bg-muted")}
          >
            {s.device === "mobile" ? <Smartphone className="h-3 w-3" /> : <Monitor className="h-3 w-3" />}
            {PAGE_LABELS[s.page] ?? s.page}
          </button>
        ))}
      </div>
      <Dialog open={zoom} onOpenChange={setZoom}>
        <DialogContent className="max-w-5xl">
          <DialogTitle>{PAGE_LABELS[cur.page] ?? cur.page} · {cur.device === "mobile" ? "mobil" : "desktop"}</DialogTitle>
          <div className="max-h-[75vh] overflow-y-auto rounded border scrollbar-thin">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={cur.url} alt="" className={cn("w-full", cur.device === "mobile" && "mx-auto max-w-sm")} />
          </div>
          <a href={cur.url} target="_blank" rel="noreferrer" className="text-xs text-muted-foreground underline">Otevřít v plné velikosti</a>
        </DialogContent>
      </Dialog>
    </div>
  );
}
