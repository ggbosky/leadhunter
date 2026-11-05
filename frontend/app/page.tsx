"use client";
import Link from "next/link";
import { toast } from "sonner";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, ArrowRight, Bell, CheckCircle2, Pause, Play, Rocket, Search, Send } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/misc";
import { CategoryBadge, ScorePill } from "@/components/score";
import { post, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type Dashboard = {
  total_companies: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_segment: { segment_key: string | null; label: string; count: number; avg_score: number | null }[];
  funnel: { qualified: number; contacted: number; replied: number; meetings: number; won: number };
  activity: { date: string; discovered: number; analyzed: number; contacted: number }[];
  score_histogram: { bucket: string; count: number }[];
  followups_due: number;
  queue: Record<string, number>;
  automation_paused: boolean;
  last_report: null | {
    date: string;
    new_companies: number;
    analyzed: number;
    messages_prepared_for: number;
    followups_due_24h: number;
    top_leads: { company_id: number; name: string; segment: string | null; score: number; category: string; reason: string }[];
    failed_jobs: { id: number; type: string; error: string }[];
    sources: { key: string; name: string; status: string | null; error: string | null }[];
  };
  last_report_at: string | null;
};

type AiStatus = {
  text: { available: boolean; note: string };
  vision: { available: boolean; note: string };
  playwright: { available: boolean; note: string };
  hardware: { ram_gb: number | null; recommendation: string };
};

function Stat({ label, value, sub, href }: { label: string; value: number | string; sub?: string; href?: string }) {
  const inner = (
    <Card className="h-full transition-colors hover:border-primary/40">
      <CardContent className="p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p>
        {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
      </CardContent>
    </Card>
  );
  return href ? <Link href={href}>{inner}</Link> : inner;
}

export default function DashboardPage() {
  const { data, mutate, isLoading } = useApi<Dashboard>("/dashboard", { refreshInterval: 30000 });
  const { data: ai } = useApi<AiStatus>("/ai/status");

  async function runDaily() {
    try {
      await post("/automation/run-daily");
      toast.success("Denní automatizace zařazena do fronty");
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function togglePause() {
    await post(data?.automation_paused ? "/automation/resume" : "/automation/pause");
    toast.success(data?.automation_paused ? "Automatizace obnovena" : "Automatizace pozastavena");
    mutate();
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28" />)}</div>
        <Skeleton className="h-72" />
      </div>
    );
  }

  const qualified = (data.by_category.priority ?? 0) + (data.by_category.strong ?? 0);
  const rep = data.last_report;
  const funnel = [
    { name: "Kvalifikované", value: data.funnel.qualified },
    { name: "Oslovené", value: data.funnel.contacted },
    { name: "Odpověděly", value: data.funnel.replied },
    { name: "Schůzky", value: data.funnel.meetings },
    { name: "Klienti", value: data.funnel.won },
  ];

  return (
    <div>
      <PageHeader
        title="Přehled"
        description="Kvalitní firma + slabá digitální prezentace + ekonomický potenciál + vhodný moment = zajímavý lead."
        actions={
          <>
            <Button variant="outline" onClick={togglePause}>
              {data.automation_paused ? <Play /> : <Pause />}
              {data.automation_paused ? "Obnovit automatizaci" : "Pozastavit automatizaci"}
            </Button>
            <Button onClick={runDaily}>
              <Rocket /> Spustit denní běh
            </Button>
          </>
        }
      />

      {ai && (!ai.vision.available || !ai.text.available) && (
        <Card className="mb-6 border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30">
          <CardContent className="flex gap-3 p-4 text-sm">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
            <div className="space-y-1">
              {!ai.vision.available && (
                <p>
                  <b>Vizuální AI analýza není dostupná</b> – audity jsou označeny jako neúplné a skóre webu vychází jen z technických metrik.{" "}
                  <span className="text-muted-foreground">{ai.vision.note}</span>
                </p>
              )}
              {!ai.text.available && (
                <p>
                  <b>Textový model není dostupný</b> – zprávy skládá deterministický kompozitor z ověřených faktů.
                </p>
              )}
              <p className="text-muted-foreground">{ai.hardware.recommendation}</p>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
        <Stat label="Firem v CRM" value={data.total_companies} sub={`${data.by_status.new ?? 0} čeká na analýzu`} href="/leady" />
        <Stat label="Priority + Strong" value={qualified} sub={`${data.by_category.priority ?? 0} Priority Lead`} href="/leady?category=priority,strong" />
        <Stat label="K oslovení" value={data.by_status.qualified ?? 0} sub="kvalifikované, neoslovené" href="/osloveni" />
        <Stat label="Follow-upy dnes" value={data.followups_due} sub="po termínu nebo dnes" href="/follow-up" />
        <Stat label="Fronta úloh" value={(data.queue.queued ?? 0) + (data.queue.running ?? 0)} sub={`${data.queue.running ?? 0} běží · ${data.queue.failed ?? 0} selhalo`} href="/automatizace" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Aktivita za 14 dní</CardTitle>
            <CardDescription>Nově objevené firmy, analyzované weby a odeslaná oslovení</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data.activity.map((d) => ({ ...d, label: d.date.slice(5).split("-").reverse().join(".") }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="label" fontSize={11} tickLine={false} />
                <YAxis fontSize={11} tickLine={false} allowDecimals={false} width={30} />
                <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Area type="monotone" dataKey="discovered" name="Objeveno" stroke="#6366f1" fill="#6366f1" fillOpacity={0.15} />
                <Area type="monotone" dataKey="analyzed" name="Analyzováno" stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.15} />
                <Area type="monotone" dataKey="contacted" name="Osloveno" stroke="#10b981" fill="#10b981" fillOpacity={0.2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Obchodní trychtýř</CardTitle>
            <CardDescription>Skutečné výsledky oslovení</CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={funnel} layout="vertical" margin={{ left: 10 }}>
                <XAxis type="number" hide allowDecimals={false} />
                <YAxis type="category" dataKey="name" width={95} fontSize={12} tickLine={false} axisLine={false} />
                <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="value" name="Počet" fill="#6366f1" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Denní přehled</CardTitle>
              <CardDescription>{data.last_report_at ? `Vygenerováno ${fmtDate(data.last_report_at, true)}` : "Zatím nevygenerován – spusťte denní běh"}</CardDescription>
            </div>
            <Button asChild variant="outline" size="sm">
              <Link href="/osloveni">
                <Send /> Oslovovat
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {rep ? (
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2 text-sm">
                  <Badge variant="secondary">
                    <Search className="h-3 w-3" /> {rep.new_companies} nových firem
                  </Badge>
                  <Badge variant="secondary">
                    <CheckCircle2 className="h-3 w-3" /> {rep.analyzed} analyzováno
                  </Badge>
                  <Badge variant="secondary">
                    <Send className="h-3 w-3" /> zprávy pro {rep.messages_prepared_for} firem
                  </Badge>
                  <Badge variant="secondary">
                    <Bell className="h-3 w-3" /> {rep.followups_due_24h} follow-upů do 24 h
                  </Badge>
                </div>
                <div className="divide-y rounded-lg border">
                  {rep.top_leads.length === 0 && <p className="p-4 text-sm text-muted-foreground">Zatím žádné ohodnocené leady.</p>}
                  {rep.top_leads.map((l) => (
                    <Link key={l.company_id} href={`/leady/${l.company_id}`} className="flex items-start gap-3 p-3 hover:bg-muted/50">
                      <ScorePill value={l.score} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">
                          {l.name} <span className="font-normal text-muted-foreground">· {l.segment ?? "obor neurčen"}</span>
                        </p>
                        <p className="line-clamp-1 text-xs text-muted-foreground">{l.reason}</p>
                      </div>
                      <CategoryBadge category={l.category} />
                    </Link>
                  ))}
                </div>
                {rep.failed_jobs.length > 0 && (
                  <p className="text-xs text-red-600">
                    {rep.failed_jobs.length} úloh dnes selhalo – detail v sekci <Link className="underline" href="/automatizace">Automatizace</Link>.
                  </p>
                )}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Denní přehled vznikne po prvním běhu automatizace.</p>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Rozložení Opportunity Score</CardTitle>
          </CardHeader>
          <CardContent className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.score_histogram}>
                <XAxis dataKey="bucket" fontSize={10} tickLine={false} interval={0} angle={-30} textAnchor="end" height={40} />
                <YAxis fontSize={11} allowDecimals={false} width={28} tickLine={false} />
                <Tooltip contentStyle={{ borderRadius: 8, fontSize: 12 }} />
                <Bar dataKey="count" name="Leadů" fill="#0ea5e9" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Segmenty</CardTitle>
          <CardDescription>Počet firem a průměrné Opportunity Score podle oboru</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.by_segment
              .sort((a, b) => b.count - a.count)
              .map((s) => (
                <Link key={s.segment_key ?? "none"} href={`/leady?segment=${s.segment_key ?? ""}`} className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted">
                  <span className="truncate">{s.label}</span>
                  <span className="flex items-center gap-2">
                    <span className="text-muted-foreground tabular-nums">{s.count}</span>
                    <ScorePill value={s.avg_score} />
                  </span>
                </Link>
              ))}
            {data.by_segment.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Zatím žádné firmy. Začněte v sekci <Link href="/vyhledavani" className="underline">Vyhledávání</Link> <ArrowRight className="inline h-3 w-3" />
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
