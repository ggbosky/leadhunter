"use client";
import Link from "next/link";
import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, ExternalLink, Loader2, RefreshCw, ScanSearch, Send, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScorePill } from "@/components/score";
import { useMeta } from "@/components/meta-provider";
import { ScoreBreakdown } from "@/components/lead/score-breakdown";
import { ScreenshotGallery } from "@/components/lead/screenshots";
import { ContactsPanel } from "@/components/lead/contacts-panel";
import { MessagesPanel } from "@/components/lead/messages-panel";
import { OutreachActions } from "@/components/lead/outreach-actions";
import { del, patch, post, useApi } from "@/lib/api";
import { EVENT_LABELS, fmtCzk, fmtDate, STATUS_VARIANT } from "@/lib/format";
import type { CompanyDetail } from "@/lib/types";

const SEVERITY: Record<string, "danger" | "warning" | "muted"> = { high: "danger", medium: "warning", low: "muted" };

export default function LeadDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const meta = useMeta();
  const router = useRouter();
  const { data: c, mutate, isLoading } = useApi<CompanyDetail>(`/companies/${id}`, { refreshInterval: 15000 });
  const [busy, setBusy] = useState(false);
  const [signal, setSignal] = useState({ signal_type: "new_service", description: "", evidence: "", strength: 0.5 });

  if (isLoading || !c) return <Skeleton className="h-[600px]" />;

  async function analyze() {
    setBusy(true);
    try {
      await post(`/companies/${c!.id}/analyze`);
      toast.success("Analýza zařazena do fronty – výsledek se objeví během minuty");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function update(body: Record<string, unknown>) {
    try {
      await patch(`/companies/${c!.id}`, body);
      toast.success("Uloženo");
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function remove() {
    if (!confirm(`Opravdu smazat ${c!.name} z CRM?`)) return;
    await del(`/companies/${c!.id}`);
    router.push("/leady");
  }
  async function addSignal(e: React.FormEvent) {
    e.preventDefault();
    await post(`/companies/${c!.id}/signals`, signal);
    setSignal({ ...signal, description: "", evidence: "" });
    toast.success("Signál přidán a skóre přepočítáno");
    mutate();
  }

  const draft = c.messages.find((m) => m.status === "draft" && m.message_type === "first_message");

  return (
    <div>
      <Link href="/leady" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> Zpět na leady
      </Link>
      <PageHeader
        title={c.name}
        description={[c.segment_label, c.city, c.region_name, c.legal_form].filter(Boolean).join(" · ")}
        actions={
          <>
            <Button variant="outline" onClick={analyze} disabled={busy || !c.website_url}>
              {busy ? <Loader2 className="animate-spin" /> : <ScanSearch />} Analyzovat znovu
            </Button>
            <Button variant="outline" onClick={async () => { await post(`/companies/${c.id}/rescore`); mutate(); toast.success("Skóre přepočítáno"); }}>
              <RefreshCw /> Přepočítat skóre
            </Button>
            <Button asChild>
              <Link href={`/osloveni?company=${c.id}`}><Send /> Oslovit</Link>
            </Button>
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2 text-sm">
        <Badge variant={STATUS_VARIANT[c.status] ?? "muted"}>{meta?.statuses[c.status] ?? c.status}</Badge>
        {c.tier && <Badge variant="outline">Tier {c.tier}</Badge>}
        {c.website_url ? (
          <a href={c.website_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline">
            {c.domain} <ExternalLink className="h-3 w-3" />
          </a>
        ) : (
          <Badge variant="warning">Bez webu</Badge>
        )}
        {c.ico && <span className="text-muted-foreground">IČO {c.ico}</span>}
        {Object.entries(c.social_links ?? {}).map(([k, v]) => (
          <a key={k} href={v} target="_blank" rel="noreferrer" className="text-muted-foreground hover:underline">{k}</a>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Hodnocení příležitosti</CardTitle>
              {c.score?.outreach_reason && <CardDescription className="text-foreground/80">{c.score.outreach_reason}</CardDescription>}
            </CardHeader>
            <CardContent><ScoreBreakdown score={c.score} /></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Správa leadu</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1">
                <Label>Obor</Label>
                <NativeSelect value={c.segment_key ?? ""} onChange={(e) => update({ segment_key: e.target.value || null })}>
                  <option value="">Neurčeno</option>
                  {meta?.segments.map((s) => <option key={s.key} value={s.key}>{s.label} (Tier {s.tier})</option>)}
                </NativeSelect>
              </div>
              <div className="space-y-1">
                <Label>Stav</Label>
                <NativeSelect value={c.status} onChange={(e) => update({ status: e.target.value })}>
                  {meta && Object.entries(meta.statuses).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </NativeSelect>
              </div>
              <div className="space-y-1">
                <Label>Poznámky</Label>
                <Textarea defaultValue={c.notes ?? ""} rows={3} onBlur={(e) => e.target.value !== (c.notes ?? "") && update({ notes: e.target.value })} />
              </div>
              <Button variant="ghost" size="sm" className="text-red-600" onClick={remove}><Trash2 /> Smazat z CRM</Button>
            </CardContent>
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          <Card>
            <CardContent className="p-5"><OutreachActions companyId={c.id} messageId={draft?.id} onDone={mutate} /></CardContent>
          </Card>
          <Tabs defaultValue="visual">
            <TabsList>
              <TabsTrigger value="visual">Vizuální analýza</TabsTrigger>
              <TabsTrigger value="audit">Technický audit</TabsTrigger>
              <TabsTrigger value="signals">Signály ({c.signals.length})</TabsTrigger>
              <TabsTrigger value="contacts">Kontakty & LinkedIn ({c.contacts.length})</TabsTrigger>
              <TabsTrigger value="messages">Zprávy</TabsTrigger>
              <TabsTrigger value="history">Historie</TabsTrigger>
              <TabsTrigger value="data">Data</TabsTrigger>
            </TabsList>

            <TabsContent value="visual">
              <div className="grid gap-6 xl:grid-cols-[1fr_1fr]">
                <ScreenshotGallery audit={c.audit} />
                <div className="space-y-3">
                  {!c.visual && <p className="text-sm text-muted-foreground">Vizuální analýza zatím neproběhla.</p>}
                  {c.visual && c.visual.status !== "complete" && (
                    <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30">
                      <p className="font-medium">Audit je neúplný</p>
                      <p className="text-muted-foreground">{c.visual.error}</p>
                    </div>
                  )}
                  {c.visual?.status === "complete" && (
                    <>
                      <div className="flex items-center gap-3">
                        <ScorePill value={c.visual.visual_score} className="text-base px-2 py-1" />
                        <div>
                          <p className="font-medium">Website Visual Score</p>
                          <p className="text-xs text-muted-foreground">
                            Expertní odhad AI ({c.visual.provider} · {c.visual.model}) · jistota {Math.round((c.visual.confidence ?? 0) * 100)} %
                            {c.visual.design_era && ` · design odpovídá období ${c.visual.design_era}`}
                          </p>
                        </div>
                      </div>
                      {c.visual.summary && <p className="text-sm">{c.visual.summary}</p>}
                      {c.visual.business_impression && <p className="text-sm text-muted-foreground"><b>Dojem z podnikání:</b> {c.visual.business_impression}</p>}
                      <div className="grid gap-3 sm:grid-cols-2">
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">Hlavní problémy</p>
                          <ul className="list-disc pl-4 text-sm">{c.visual.top_issues.map((t, i) => <li key={i}>{t}</li>)}</ul>
                        </div>
                        <div>
                          <p className="text-xs font-medium text-muted-foreground">Silné stránky</p>
                          <ul className="list-disc pl-4 text-sm">{c.visual.strengths.map((t, i) => <li key={i}>{t}</li>)}</ul>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              </div>
              {c.visual?.status === "complete" && (
                <Card className="mt-6">
                  <Table>
                    <THead><TR><TH>Kritérium</TH><TH>Skóre</TH><TH>Pozorování a důkaz</TH><TH>Doporučení</TH><TH>Jistota</TH></TR></THead>
                    <TBody>
                      {c.visual.criteria.map((cr) => (
                        <TR key={cr.key}>
                          <TD className="font-medium whitespace-nowrap">{cr.label}</TD>
                          <TD><ScorePill value={cr.score} /></TD>
                          <TD className="text-xs"><p>{cr.observation}</p>{cr.evidence && <p className="mt-1 text-muted-foreground">Důkaz: {cr.evidence}</p>}</TD>
                          <TD className="text-xs">{cr.recommendation}</TD>
                          <TD className="text-xs tabular-nums">{Math.round(cr.confidence * 100)} %</TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                  <p className="p-3 text-[11px] text-muted-foreground">Subjektivní estetické závěry jsou expertní odhady modelu, nikoli objektivní měření.</p>
                </Card>
              )}
            </TabsContent>

            <TabsContent value="audit">
              {!c.audit ? (
                <p className="text-sm text-muted-foreground">{c.website?.last_error ? `Web nedostupný: ${c.website.last_error}` : "Audit zatím neproběhl."}</p>
              ) : (
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <ScorePill value={c.audit.technical_score} className="text-base px-2 py-1" />
                    <div>
                      <p className="font-medium">Technické skóre</p>
                      <p className="text-xs text-muted-foreground">Objektivní měření (HTTPS, responzivita, rychlost, HTML, CTA…) · {fmtDate(c.audit.created_at, true)}</p>
                    </div>
                  </div>
                  <div className="space-y-2">
                    {c.audit.issues.map((i) => (
                      <div key={i.code} className="flex items-start gap-3 rounded-lg border p-3">
                        <Badge variant={SEVERITY[i.severity] ?? "muted"}>{i.severity === "high" ? "vysoká" : i.severity === "medium" ? "střední" : "nízká"}</Badge>
                        <div>
                          <p className="text-sm font-medium">{i.title}</p>
                          <p className="text-xs text-muted-foreground">{i.detail}</p>
                        </div>
                      </div>
                    ))}
                    {c.audit.issues.length === 0 && <p className="text-sm text-muted-foreground">Žádné technické problémy nenalezeny.</p>}
                  </div>
                  {c.website && (
                    <p className="text-xs text-muted-foreground">
                      CMS: {c.website.cms ?? "neznámé"} · Technologie: {c.website.technologies.join(", ") || "—"} · robots.txt: {c.website.robots_allowed === false ? "zakázáno" : "povoleno"}
                    </p>
                  )}
                </div>
              )}
            </TabsContent>

            <TabsContent value="signals">
              <div className="space-y-2">
                {c.signals.map((s) => (
                  <div key={s.id} className="flex items-start justify-between gap-3 rounded-lg border p-3 text-sm">
                    <div>
                      <p className="font-medium">{s.description} <Badge variant="muted" className="ml-1">{meta?.signal_types[s.signal_type] ?? s.signal_type}</Badge></p>
                      {s.evidence && <p className="text-xs text-muted-foreground">„{s.evidence}“</p>}
                      {s.source_url && <a href={s.source_url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline">zdroj</a>}
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs tabular-nums text-muted-foreground">síla {Math.round(s.strength * 100)} %</span>
                      <Button size="icon" variant="ghost" onClick={async () => { await del(`/signals/${s.id}`); mutate(); }}><Trash2 /></Button>
                    </div>
                  </div>
                ))}
                {c.signals.length === 0 && <p className="text-sm text-muted-foreground">Nenalezeny žádné signály investice. Můžete přidat vlastní zjištění.</p>}
              </div>
              <form onSubmit={addSignal} className="mt-4 grid gap-2 rounded-lg border p-3 sm:grid-cols-[180px_1fr_1fr_auto]">
                <NativeSelect value={signal.signal_type} onChange={(e) => setSignal({ ...signal, signal_type: e.target.value })}>
                  {meta && Object.entries(meta.signal_types).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </NativeSelect>
                <Input required placeholder="Popis signálu" value={signal.description} onChange={(e) => setSignal({ ...signal, description: e.target.value })} />
                <Input placeholder="Důkaz / zdroj" value={signal.evidence} onChange={(e) => setSignal({ ...signal, evidence: e.target.value })} />
                <Button type="submit">Přidat</Button>
              </form>
            </TabsContent>

            <TabsContent value="contacts"><ContactsPanel company={c} onChanged={mutate} /></TabsContent>
            <TabsContent value="messages"><MessagesPanel companyId={c.id} messages={c.messages} onChanged={mutate} /></TabsContent>

            <TabsContent value="history">
              <div className="grid gap-6 md:grid-cols-2">
                <div>
                  <p className="mb-2 text-sm font-medium">Komunikace</p>
                  <ol className="space-y-2 border-l pl-4">
                    {c.events.map((e) => (
                      <li key={e.id} className="text-sm">
                        <p className="font-medium">{EVENT_LABELS[e.event_type] ?? e.event_type} {e.strategy && <Badge variant="outline">Strategie {e.strategy}</Badge>}</p>
                        <p className="text-xs text-muted-foreground">{fmtDate(e.occurred_at, true)}{e.notes ? ` · ${e.notes}` : ""}</p>
                      </li>
                    ))}
                    {c.events.length === 0 && <li className="text-sm text-muted-foreground">Zatím žádná komunikace.</li>}
                  </ol>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">Úkoly</p>
                  <div className="space-y-1">
                    {c.tasks.map((t) => (
                      <div key={t.id} className="flex justify-between gap-2 rounded-md border p-2 text-xs">
                        <span>{t.title}</span>
                        <span className="text-muted-foreground">{fmtDate(t.due_at)} · {t.status}</span>
                      </div>
                    ))}
                    {c.tasks.length === 0 && <p className="text-sm text-muted-foreground">Žádné úkoly.</p>}
                  </div>
                  <p className="mb-2 mt-4 text-sm font-medium">Vývoj skóre</p>
                  <div className="space-y-1 text-xs">
                    {c.score_history.map((h, i) => (
                      <div key={i} className="flex justify-between"><span className="text-muted-foreground">{fmtDate(h.computed_at, true)}</span><ScorePill value={h.opportunity_score} /></div>
                    ))}
                  </div>
                </div>
              </div>
            </TabsContent>

            <TabsContent value="data">
              <div className="grid gap-6 md:grid-cols-2">
                <Card>
                  <CardHeader><CardTitle className="text-sm">Firma a registr</CardTitle></CardHeader>
                  <CardContent className="space-y-1 text-sm">
                    {[
                      ["Obchodní jméno", c.legal_name], ["IČO", c.ico], ["Právní forma", c.legal_form], ["Vznik", c.founded_on],
                      ["Stav v registru", c.registry_status], ["Základní kapitál", c.registered_capital ? fmtCzk(c.registered_capital) : null],
                      ["Adresa", [c.street, c.postcode, c.city].filter(Boolean).join(", ")], ["Telefon", c.phone], ["E-mail", c.email],
                      ["Otevírací doba", c.opening_hours], ["NACE", c.nace_codes?.slice(0, 8).join(", ")],
                    ].map(([k, v]) => (
                      <div key={k as string} className="flex justify-between gap-3"><span className="text-muted-foreground">{k}</span><span className="text-right">{(v as string) || "—"}</span></div>
                    ))}
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader><CardTitle className="text-sm">Zdroje dat</CardTitle></CardHeader>
                  <CardContent className="space-y-1 text-xs">
                    {c.sources.map((s, i) => (
                      <div key={i} className="flex justify-between gap-2">
                        <span>{s.source}</span>
                        {s.url ? <a href={s.url} target="_blank" rel="noreferrer" className="text-primary hover:underline">{s.external_id}</a> : <span>{s.external_id}</span>}
                      </div>
                    ))}
                    <p className="pt-2 text-muted-foreground">Nalezeno {c.times_seen}× · poprvé {fmtDate(c.first_seen_at)}</p>
                  </CardContent>
                </Card>
                {c.website && (
                  <Card className="md:col-span-2">
                    <CardHeader><CardTitle className="text-sm">Fakta z webu</CardTitle></CardHeader>
                    <CardContent>
                      <pre className="max-h-96 overflow-auto rounded bg-muted p-3 text-[11px] scrollbar-thin">{JSON.stringify(c.website.facts, null, 2)}</pre>
                      <div className="mt-3 flex gap-2">
                        <Input placeholder="Opravit adresu webu…" defaultValue={c.website_url ?? ""} onKeyDown={(e) => {
                          if (e.key === "Enter") update({ website_url: (e.target as HTMLInputElement).value });
                        }} />
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
