"use client";
import Link from "next/link";
import { Fragment, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";
import {
  CalendarClock,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Copy,
  ExternalLink,
  Keyboard,
  Linkedin,
  Loader2,
  MessageSquareText,
  ThumbsDown,
  UserPlus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { CategoryBadge, ScorePill, ScoreRing } from "@/components/score";
import { ScreenshotGallery } from "@/components/lead/screenshots";
import { copyText, MessagesPanel, TYPE_ORDER } from "@/components/lead/messages-panel";
import { FollowUpDialog } from "@/components/lead/outreach-actions";
import { useMeta } from "@/components/meta-provider";
import { post, useApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { CompanyDetail, LeadSummary } from "@/lib/types";

type Queue = { items: LeadSummary[]; total: number };

const SHORTCUTS: [string, string][] = [
  ["C", "Kopírovat zprávu"],
  ["L", "Otevřít LinkedIn"],
  ["M", "Označit jako osloveno"],
  ["R", "Žádost o spojení odeslána"],
  ["F", "Naplánovat follow-up"],
  ["N", "Nemá zájem"],
  ["G", "Vygenerovat zprávy"],
  ["1–5", "Typ zprávy"],
  ["J / →", "Další lead"],
  ["K / ←", "Předchozí lead"],
];

function QuickContact({ company, onSaved }: { company: CompanyDetail; onSaved: () => void }) {
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  async function save(e: React.FormEvent) {
    e.preventDefault();
    try {
      await post(`/companies/${company.id}/contacts`, { name, role: role || null, linkedin_url: url || null, is_primary: true, is_decision_maker: true });
      toast.success("Profil uložen");
      setUrl(""); setName(""); setRole("");
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }
  return (
    <form onSubmit={save} className="grid gap-2 sm:grid-cols-[1fr_1fr_1.4fr_auto]">
      <Input required placeholder="Jméno" value={name} onChange={(e) => setName(e.target.value)} />
      <Input placeholder="Pozice (Founder…)" value={role} onChange={(e) => setRole(e.target.value)} />
      <Input placeholder="https://www.linkedin.com/in/…" value={url} onChange={(e) => setUrl(e.target.value)} />
      <Button type="submit" size="sm" className="h-9">Uložit</Button>
    </form>
  );
}

function Workspace() {
  const meta = useMeta();
  const sp = useSearchParams();
  const [minScore, setMinScore] = useState(40);
  const [segment, setSegment] = useState("");
  const { data: queue, mutate: mutateQueue, isLoading } = useApi<Queue>(`/outreach/queue?min_score=${minScore}${segment ? `&segment=${segment}` : ""}`);
  const [currentId, setCurrentId] = useState<number | null>(sp.get("company") ? Number(sp.get("company")) : null);
  const [msgType, setMsgType] = useState("connection_request");
  const [fuOpen, setFuOpen] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [done, setDone] = useState(0);
  const startedAt = useRef<number>(Date.now());

  const items = useMemo(() => queue?.items ?? [], [queue]);
  useEffect(() => {
    if (currentId === null && items.length) setCurrentId(items[0].id);
  }, [items, currentId]);

  const { data: lead, mutate: mutateLead } = useApi<CompanyDetail>(currentId ? `/companies/${currentId}` : null);
  const idx = items.findIndex((i) => i.id === currentId);
  const drafts = useMemo(() => (lead?.messages ?? []).filter((m) => m.status === "draft"), [lead]);
  const currentMsg = drafts.find((m) => m.message_type === msgType) ?? drafts[0];
  const contact = lead?.contacts.find((c) => c.id === lead.best_contact_id) ?? null;

  useEffect(() => {
    startedAt.current = Date.now();
    // výchozí typ: bez spojení → žádost; spojeno → první zpráva
    if (contact?.connection_status === "connected") setMsgType("first_message");
    else setMsgType("connection_request");
  }, [currentId, contact?.connection_status]);

  const go = useCallback((delta: number) => {
    if (!items.length) return;
    const i = idx < 0 ? 0 : Math.min(items.length - 1, Math.max(0, idx + delta));
    setCurrentId(items[i].id);
  }, [idx, items]);

  const advanceAfterAction = useCallback(async () => {
    const nextItem = items[idx + 1] ?? items[idx - 1] ?? null;
    setDone((d) => d + 1);
    await mutateQueue();
    setCurrentId(nextItem ? nextItem.id : null);
  }, [idx, items, mutateQueue]);

  const copy = useCallback(async () => {
    const el = document.querySelector<HTMLTextAreaElement>("#workspace-messages textarea");
    const text = el?.value ?? currentMsg?.content;
    if (text && (await copyText(text))) toast.success("Zpráva zkopírována");
  }, [currentMsg]);

  const openLinkedIn = useCallback(() => {
    if (!lead) return;
    const url = contact?.linkedin_url ?? lead.linkedin.links.find((l) => l.label.startsWith("Rozhodovací"))?.url ?? lead.linkedin.links[0]?.url;
    if (url) window.open(url, "_blank", "noopener");
  }, [lead, contact]);

  const markContacted = useCallback(async (kind: "message_sent" | "connection_requested") => {
    if (!lead) return;
    try {
      const msgId = kind === "connection_requested"
        ? drafts.find((m) => m.message_type === "connection_request")?.id
        : (currentMsg?.message_type === "connection_request" ? drafts.find((m) => m.message_type === "first_message")?.id : currentMsg?.id);
      await post(`/companies/${lead.id}/outreach/contacted`, { kind, message_id: msgId, contact_id: contact?.id });
      const secs = Math.round((Date.now() - startedAt.current) / 1000);
      toast.success(`${lead.name}: ${kind === "connection_requested" ? "žádost o spojení" : "osloveno"} (${secs} s)`);
      await advanceAfterAction();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }, [lead, drafts, currentMsg, contact, advanceAfterAction]);

  const notInterested = useCallback(async () => {
    if (!lead) return;
    const explicit = confirm(`${lead.name}: výslovně odmítl kontaktování?\n\nOK = Do Not Contact\nZrušit = jen nezájem / nevhodný lead`);
    await post(`/companies/${lead.id}/outreach/not-interested`, { explicit_refusal: explicit });
    toast.success(explicit ? "Přidáno na Do Not Contact" : "Lead vyřazen");
    await advanceAfterAction();
  }, [lead, advanceAfterAction]);

  const generate = useCallback(async () => {
    if (!lead) return;
    setGenerating(true);
    try {
      await post(`/companies/${lead.id}/messages/generate`, { strategy: "auto" });
      await mutateLead();
      mutateQueue();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }, [lead, mutateLead, mutateQueue]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const t = e.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "j" || e.key === "ArrowRight") go(1);
      else if (k === "k" || e.key === "ArrowLeft") go(-1);
      else if (k === "c") copy();
      else if (k === "l") openLinkedIn();
      else if (k === "m") markContacted("message_sent");
      else if (k === "r") markContacted("connection_requested");
      else if (k === "f") setFuOpen(true);
      else if (k === "n") notInterested();
      else if (k === "g") generate();
      else if (k === "?") setShowHelp((s) => !s);
      else if (/^[1-5]$/.test(k)) setMsgType(TYPE_ORDER[Number(k) - 1]);
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, copy, openLinkedIn, markContacted, notInterested, generate]);

  const issues = useMemo(() => {
    if (!lead) return [] as string[];
    const vis = lead.visual?.status === "complete" ? lead.visual.top_issues : [];
    return [...vis, ...(lead.audit?.issues ?? []).filter((i) => i.severity !== "low").map((i) => i.title)].slice(0, 5);
  }, [lead]);

  return (
    <div className="grid gap-4 lg:grid-cols-[280px_1fr]">
      <aside className="space-y-3">
        <div>
          <h1 className="text-xl font-semibold">Oslovování</h1>
          <p className="text-xs text-muted-foreground">{queue ? `${queue.total} leadů ve frontě` : "…"} · dnes zpracováno {done}</p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <NativeSelect value={minScore} onChange={(e) => { setMinScore(Number(e.target.value)); setCurrentId(null); }}>
            <option value={0}>Skóre: vše</option>
            <option value={40}>Skóre 40+</option>
            <option value={60}>Skóre 60+</option>
            <option value={80}>Skóre 80+</option>
          </NativeSelect>
          <NativeSelect value={segment} onChange={(e) => { setSegment(e.target.value); setCurrentId(null); }}>
            <option value="">Všechny obory</option>
            {meta?.segments.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </NativeSelect>
        </div>
        <div className="max-h-[calc(100vh-220px)] space-y-1 overflow-y-auto pr-1 scrollbar-thin">
          {isLoading && <Skeleton className="h-64" />}
          {items.map((i) => (
            <button key={i.id} onClick={() => setCurrentId(i.id)}
              className={cn("flex w-full items-center gap-2 rounded-lg border p-2 text-left text-sm cursor-pointer", i.id === currentId ? "border-primary bg-accent" : "bg-card hover:bg-muted")}>
              <ScorePill value={i.opportunity_score} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">{i.name}</span>
                <span className="block truncate text-[11px] text-muted-foreground">{i.segment_label ?? "—"}{i.city ? ` · ${i.city}` : ""}</span>
              </span>
              <span className="flex gap-0.5">
                {i.has_messages && <MessageSquareText className="h-3.5 w-3.5 text-emerald-600" aria-label="zpráva připravena" />}
                {i.has_linkedin && <Linkedin className="h-3.5 w-3.5 text-sky-700" aria-label="LinkedIn uložen" />}
              </span>
            </button>
          ))}
        </div>
        <button className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground cursor-pointer" onClick={() => setShowHelp((s) => !s)}>
          <Keyboard className="h-3.5 w-3.5" /> Klávesové zkratky (?)
        </button>
        {showHelp && (
          <Card><CardContent className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 p-3 text-xs">
            {SHORTCUTS.map(([k, v]) => (<Fragment key={k}><kbd className="justify-self-start">{k}</kbd><span>{v}</span></Fragment>))}
          </CardContent></Card>
        )}
      </aside>

      <section className="min-w-0">
        {!isLoading && items.length === 0 && !lead && (
          <EmptyState title="Fronta je prázdná" description="Žádné kvalifikované neoslovené leady nad zvoleným skóre. Snižte filtr nebo spusťte vyhledávání a analýzu."
            action={<Button asChild><Link href="/vyhledavani">Najít další firmy</Link></Button>} />
        )}
        {currentId && !lead && <Skeleton className="h-[600px]" />}
        {lead && (
          <div className="space-y-4">
            <Card>
              <CardContent className="flex flex-wrap items-start gap-4 p-5">
                <ScoreRing value={lead.opportunity_score} />
                <div className="min-w-0 flex-1 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/leady/${lead.id}`} className="text-xl font-semibold hover:underline">{lead.name}</Link>
                    <CategoryBadge category={lead.category} label={lead.category_label} />
                    {lead.website_url && (
                      <a href={lead.website_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sm text-primary hover:underline">
                        {lead.domain} <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">{[lead.segment_label, lead.city, lead.legal_form].filter(Boolean).join(" · ")}</p>
                  {lead.score?.outreach_reason && <p className="text-sm"><b>Důvod oslovení:</b> {lead.score.outreach_reason}</p>}
                  <div className="flex flex-wrap gap-3 pt-1 text-xs text-muted-foreground">
                    <span>Design Gap <ScorePill value={lead.score?.design_gap} /></span>
                    <span>Komerční <ScorePill value={lead.score?.commercial_potential} /></span>
                    <span>Připravenost <ScorePill value={lead.score?.buying_readiness} /></span>
                    <span>Kontakt <ScorePill value={lead.score?.contactability} /></span>
                    {lead.score?.estimated_budget && <span>Nabídka: {lead.score.estimated_budget.label}</span>}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button variant="outline" size="icon" onClick={() => go(-1)} disabled={idx <= 0} title="Předchozí (K)"><ChevronLeft /></Button>
                  <Button variant="outline" size="icon" onClick={() => go(1)} disabled={idx >= items.length - 1} title="Další (J)"><ChevronRight /></Button>
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
              <Card>
                <CardContent className="space-y-4 p-5">
                  <ScreenshotGallery audit={lead.audit} compact />
                  <div>
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">Hlavní problémy</p>
                    {issues.length ? (
                      <ul className="list-disc space-y-0.5 pl-4 text-sm">{issues.map((t, i) => <li key={i}>{t}</li>)}</ul>
                    ) : <p className="text-sm text-muted-foreground">Bez zjištěných problémů.</p>}
                    {lead.visual?.status !== "complete" && <p className="mt-1 text-[11px] text-amber-700">Vizuální AI analýza neproběhla – jen technické metriky.</p>}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardContent className="space-y-4 p-5">
                  <div>
                    <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">LinkedIn kontakt</p>
                    {contact ? (
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-medium">{contact.name}</span>
                        <span className="text-muted-foreground">{contact.role ?? ""}</span>
                        {contact.linkedin_url ? <Badge variant="info"><Linkedin className="h-3 w-3" /> profil uložen</Badge> : <Badge variant="warning">bez LinkedIn URL</Badge>}
                        <Badge variant="outline">{contact.connection_status === "connected" ? "spojeno" : contact.connection_status === "request_sent" ? "žádost odeslána" : "bez spojení"}</Badge>
                      </div>
                    ) : <p className="text-sm text-muted-foreground">Rozhodovací osoba zatím není známá.</p>}
                    {(!contact || !contact.linkedin_url) && (
                      <div className="mt-2 space-y-2">
                        <div className="flex flex-wrap gap-1">
                          {lead.linkedin.links.slice(0, 4).map((l) => (
                            <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="rounded-md border px-2 py-1 text-xs hover:bg-muted">{l.label}</a>
                          ))}
                        </div>
                        <QuickContact company={lead} onSaved={() => { mutateLead(); mutateQueue(); }} />
                      </div>
                    )}
                  </div>
                  <div id="workspace-messages">
                    {generating ? (
                      <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Generuji personalizované zprávy…</div>
                    ) : (
                      <MessagesPanel companyId={lead.id} messages={lead.messages} onChanged={() => { mutateLead(); mutateQueue(); }} activeType={msgType} onActiveTypeChange={setMsgType} compact />
                    )}
                  </div>
                </CardContent>
              </Card>
            </div>

            <Card className="z-10 shadow-lg md:sticky md:bottom-3">
              <CardContent className="flex flex-wrap items-center gap-2 p-3">
                <Button onClick={copy} disabled={!currentMsg}><Copy /> Copy Message <kbd>C</kbd></Button>
                <Button variant="outline" onClick={openLinkedIn}><Linkedin /> Open LinkedIn <kbd>L</kbd></Button>
                <Button variant="outline" onClick={() => markContacted("connection_requested")}><UserPlus /> Žádost odeslána <kbd>R</kbd></Button>
                <Button variant="success" onClick={() => markContacted("message_sent")}><CheckCheck /> Mark as Contacted <kbd>M</kbd></Button>
                <Button variant="outline" onClick={() => setFuOpen(true)}><CalendarClock /> Schedule Follow-up <kbd>F</kbd></Button>
                <Button variant="outline" className="text-red-600" onClick={notInterested}><ThumbsDown /> Not Interested <kbd>N</kbd></Button>
                <span className="ml-auto text-xs text-muted-foreground">{idx + 1} / {items.length}</span>
              </CardContent>
            </Card>
            <FollowUpDialog open={fuOpen} onOpenChange={setFuOpen} companyId={lead.id} onDone={() => { mutateLead(); }} />
          </div>
        )}
      </section>
    </div>
  );
}

export default function OutreachPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[600px]" />}>
      <Workspace />
    </Suspense>
  );
}
