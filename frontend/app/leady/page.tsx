"use client";
import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { toast } from "sonner";
import { ExternalLink, Loader2, Plus, ScanSearch } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Skeleton, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { CategoryBadge, ScorePill } from "@/components/score";
import { useMeta } from "@/components/meta-provider";
import { post, useApi } from "@/lib/api";
import { fmtDate, STATUS_VARIANT } from "@/lib/format";
import type { LeadSummary } from "@/lib/types";
import { AddCompanyDialog } from "@/components/add-company-dialog";

type Resp = { total: number; page: number; page_size: number; items: LeadSummary[] };

function LeadsInner() {
  const meta = useMeta();
  const router = useRouter();
  const sp = useSearchParams();
  const [search, setSearch] = useState(sp.get("search") ?? "");
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [addOpen, setAddOpen] = useState(false);

  const params = useMemo(() => {
    const p = new URLSearchParams(sp.toString());
    if (!p.get("sort")) p.set("sort", "score");
    return p;
  }, [sp]);
  const { data, isLoading, mutate } = useApi<Resp>(`/leads?${params.toString()}`, { refreshInterval: 20000 });

  function setParam(k: string, v: string) {
    const p = new URLSearchParams(sp.toString());
    if (v) p.set(k, v);
    else p.delete(k);
    if (k !== "page") p.delete("page");
    router.replace(`/leady?${p.toString()}`);
  }

  async function analyze(ids: number[]) {
    setBusy((b) => new Set([...b, ...ids]));
    try {
      for (const id of ids) await post(`/companies/${id}/analyze`);
      toast.success(`${ids.length} analýz zařazeno do fronty`);
      setSelected(new Set());
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setTimeout(() => setBusy(new Set()), 1500);
      mutate();
    }
  }

  const page = Number(sp.get("page") ?? 1);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div>
      <PageHeader
        title="Leady"
        description={data ? `${data.total} firem odpovídá filtru` : "Načítám…"}
        actions={
          <>
            {selected.size > 0 && (
              <Button variant="outline" onClick={() => analyze([...selected])}>
                <ScanSearch /> Analyzovat vybrané ({selected.size})
              </Button>
            )}
            <Button onClick={() => setAddOpen(true)}>
              <Plus /> Přidat firmu
            </Button>
          </>
        }
      />
      <AddCompanyDialog open={addOpen} onOpenChange={setAddOpen} onCreated={(id) => router.push(`/leady/${id}`)} />

      <Card className="mb-4 p-3">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-8">
          <form
            className="lg:col-span-2"
            onSubmit={(e) => {
              e.preventDefault();
              setParam("search", search);
            }}
          >
            <Input placeholder="Hledat název, doménu, IČO…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </form>
          <NativeSelect value={sp.get("segment") ?? ""} onChange={(e) => setParam("segment", e.target.value)}>
            <option value="">Všechny obory</option>
            {[1, 2, 3].map((t) => (
              <optgroup key={t} label={`Tier ${t}`}>
                {meta?.segments.filter((s) => s.tier === t).map((s) => (
                  <option key={s.key} value={s.key}>{s.label}</option>
                ))}
              </optgroup>
            ))}
          </NativeSelect>
          <NativeSelect value={sp.get("region") ?? ""} onChange={(e) => setParam("region", e.target.value)}>
            <option value="">Všechny regiony</option>
            {meta?.regions.map((r) => (
              <option key={r.code} value={r.code}>{r.name}</option>
            ))}
          </NativeSelect>
          <NativeSelect value={sp.get("category") ?? ""} onChange={(e) => setParam("category", e.target.value)}>
            <option value="">Všechny kategorie</option>
            <option value="priority,strong">Priority + Strong</option>
            {meta && Object.entries(meta.categories).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </NativeSelect>
          <NativeSelect value={sp.get("status") ?? ""} onChange={(e) => setParam("status", e.target.value)}>
            <option value="">Všechny stavy</option>
            {meta && Object.entries(meta.statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </NativeSelect>
          <NativeSelect value={sp.get("has_website") ?? ""} onChange={(e) => setParam("has_website", e.target.value)}>
            <option value="">Web: vše</option>
            <option value="true">Má web</option>
            <option value="false">Nemá web</option>
          </NativeSelect>
          <NativeSelect value={sp.get("sort") ?? "score"} onChange={(e) => setParam("sort", e.target.value)}>
            <option value="score">Řadit: Opportunity</option>
            <option value="design_gap">Řadit: Design Gap</option>
            <option value="confidence">Řadit: Jistota</option>
            <option value="newest">Řadit: Nejnovější</option>
            <option value="analyzed">Řadit: Naposledy analyzované</option>
            <option value="name">Řadit: Název</option>
          </NativeSelect>
        </div>
      </Card>

      {isLoading ? (
        <Skeleton className="h-96" />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="Žádné leady" description="Upravte filtr nebo spusťte vyhledávání nových firem." action={<Button asChild><Link href="/vyhledavani">Vyhledat firmy</Link></Button>} />
      ) : (
        <Card>
          <Table>
            <THead>
              <TR>
                <TH className="w-8">
                  <input
                    type="checkbox"
                    aria-label="Vybrat vše"
                    checked={selected.size === data.items.length}
                    onChange={(e) => setSelected(e.target.checked ? new Set(data.items.map((i) => i.id)) : new Set())}
                  />
                </TH>
                <TH>Web</TH>
                <TH>Firma</TH>
                <TH title="Opportunity Score">Opp.</TH>
                <TH title="Design Gap">Gap</TH>
                <TH title="Commercial Potential">Komerč.</TH>
                <TH title="Buying Readiness">Připr.</TH>
                <TH title="Kvalita webu">Web</TH>
                <TH>Kategorie</TH>
                <TH>Stav</TH>
                <TH>Analýza</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {data.items.map((l) => (
                <TR key={l.id}>
                  <TD>
                    <input
                      type="checkbox"
                      aria-label={`Vybrat ${l.name}`}
                      checked={selected.has(l.id)}
                      onChange={(e) => {
                        const s = new Set(selected);
                        if (e.target.checked) s.add(l.id);
                        else s.delete(l.id);
                        setSelected(s);
                      }}
                    />
                  </TD>
                  <TD className="w-24">
                    {l.hero_screenshot ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={l.hero_screenshot.url} alt="" className="h-12 w-20 rounded border object-cover object-top" loading="lazy" />
                    ) : (
                      <div className="grid h-12 w-20 place-items-center rounded border bg-muted text-[10px] text-muted-foreground">
                        {l.website_url ? "bez náhledu" : "bez webu"}
                      </div>
                    )}
                  </TD>
                  <TD className="max-w-xs">
                    <Link href={`/leady/${l.id}`} className="font-medium hover:underline">{l.name}</Link>
                    <p className="truncate text-xs text-muted-foreground">
                      {[l.segment_label, l.city].filter(Boolean).join(" · ") || "—"}
                      {l.domain && (
                        <a href={l.website_url ?? "#"} target="_blank" rel="noreferrer" className="ml-1 inline-flex items-center gap-0.5 hover:underline">
                          {l.domain} <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </p>
                  </TD>
                  <TD><ScorePill value={l.opportunity_score} /></TD>
                  <TD><ScorePill value={l.design_gap} /></TD>
                  <TD><ScorePill value={l.commercial_potential} /></TD>
                  <TD><ScorePill value={l.buying_readiness} /></TD>
                  <TD>
                    <span title={l.website_quality_basis === "technical" ? "Pouze technické skóre (bez vizuální AI)" : l.website_quality_basis ?? ""}>
                      <ScorePill value={l.website_quality} className={l.website_quality_basis === "technical" ? "border-dashed" : ""} />
                    </span>
                  </TD>
                  <TD><CategoryBadge category={l.category} label={l.category_label} /></TD>
                  <TD><Badge variant={STATUS_VARIANT[l.status] ?? "muted"}>{meta?.statuses[l.status] ?? l.status}</Badge></TD>
                  <TD className="text-xs text-muted-foreground whitespace-nowrap">{fmtDate(l.last_analyzed_at)}</TD>
                  <TD>
                    {l.website_url && (
                      <Button size="sm" variant="ghost" disabled={busy.has(l.id)} onClick={() => analyze([l.id])} title="Analyzovat web">
                        {busy.has(l.id) ? <Loader2 className="animate-spin" /> : <ScanSearch />}
                      </Button>
                    )}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <div className="flex items-center justify-between border-t p-3 text-sm">
            <span className="text-muted-foreground">Strana {page} z {pages}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setParam("page", String(page - 1))}>Předchozí</Button>
              <Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setParam("page", String(page + 1))}>Další</Button>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

export default function LeadsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <LeadsInner />
    </Suspense>
  );
}
