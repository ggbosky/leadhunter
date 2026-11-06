"use client";
import { Fragment, useState } from "react";
import { toast } from "sonner";
import { Pause, Play, RefreshCw, Rocket, RotateCcw, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/input";
import { Skeleton, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useMeta } from "@/components/meta-provider";
import { post, useApi } from "@/lib/api";
import { fmtDate, fmtRelative, JOB_STATUS } from "@/lib/format";
import type { Job } from "@/lib/types";

type Status = {
  config: Record<string, number | boolean | string>;
  paused: boolean;
  scheduler_running: boolean;
  next_runs: { id: string; next_run: string | null }[];
  worker_running: boolean;
  worker_threads: number;
  worker_current: Record<string, number | null>;
  last_24h: Record<string, number>;
};

const RUN_LABELS: Record<string, string> = { daily_pipeline: "Denní automatizace", followup_check: "Kontrola follow-upů", check_sources: "Kontrola zdrojů" };

function summary(j: Job): string {
  const r = j.result as Record<string, unknown> | null;
  if (!r) return j.last_error ? j.last_error.split("\n")[0] : "";
  if (j.job_type === "discover") return `nalezeno ${r.found}, nových ${r.created}, aktualizováno ${r.updated}`;
  if (j.job_type === "analyze") return `skóre ${r.opportunity_score ?? "—"} (${r.category ?? ""})`;
  if (j.job_type === "analyze_batch") return `naplánováno ${r.enqueued} analýz`;
  if (j.job_type === "prepare_messages") return `zprávy pro ${r.prepared} leadů`;
  if (j.job_type === "daily_pipeline") return `${(r.discovery_queries as string[] | undefined)?.length ?? 0} vyhledávání`;
  if (j.job_type === "followup_check") return `${r.due} follow-upů k vyřízení`;
  if (j.job_type === "score_all") return `přepočteno ${r.rescored}`;
  return "";
}

export default function AutomationPage() {
  const meta = useMeta();
  const [filter, setFilter] = useState("");
  const { data: st, mutate: mutateSt } = useApi<Status>("/automation", { refreshInterval: 5000 });
  const { data: jobs, mutate, isLoading } = useApi<Job[]>(`/jobs?limit=150${filter ? `&status=${filter}` : ""}`, { refreshInterval: 5000 });
  const [open, setOpen] = useState<number | null>(null);

  async function act(path: string, msg: string) {
    try {
      await post(path);
      toast.success(msg);
      mutate();
      mutateSt();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function job(job_type: string, label: string, payload: Record<string, unknown> = {}) {
    try {
      await post("/jobs", { job_type, payload });
      toast.success(`${label}: zařazeno do fronty`);
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div>
      <PageHeader
        title="Automatizace"
        description="Fronta úloh, plánovač a monitoring. Automatizace běží v backendu i bez otevřeného prohlížeče."
        actions={
          <>
            <Button variant="outline" onClick={() => act(st?.paused ? "/automation/resume" : "/automation/pause", st?.paused ? "Obnoveno" : "Pozastaveno")}>
              {st?.paused ? <Play /> : <Pause />} {st?.paused ? "Obnovit" : "Pozastavit"}
            </Button>
            <Button onClick={() => act("/automation/run-daily", "Denní běh zařazen")}><Rocket /> Spustit denní běh</Button>
          </>
        }
      />
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader><CardTitle className="text-sm">Stav</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            <p>Automatizace: {st?.paused ? <Badge variant="warning">pozastavena</Badge> : <Badge variant="success">aktivní</Badge>}</p>
            <p>Plánovač: {st?.scheduler_running ? <Badge variant="success">běží</Badge> : <Badge variant="danger">neběží</Badge>}</p>
            <p>Worker: {st?.worker_running ? <Badge variant="success">{st.worker_threads} vlákna</Badge> : <Badge variant="danger">neběží</Badge>}</p>
            {st?.paused && <p className="text-xs text-muted-foreground">Při pozastavení běží jen ručně spuštěné úlohy.</p>}
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Další spuštění</CardTitle></CardHeader>
          <CardContent className="space-y-1 text-sm">
            {st?.next_runs.map((r) => (
              <p key={r.id} className="flex justify-between gap-2"><span>{RUN_LABELS[r.id] ?? r.id}</span><span className="text-muted-foreground">{r.next_run ? `${fmtDate(r.next_run, true)}` : "—"}</span></p>
            ))}
            <p className="pt-1 text-xs text-muted-foreground">Denní cíle: {String(st?.config.daily_discovery_target ?? "—")} firem, {String(st?.config.daily_analysis_target ?? "—")} analýz, {String(st?.config.daily_message_target ?? "—")} zpráv (maxima, ne garance).</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="text-sm">Ruční spuštění</CardTitle><CardDescription>Jednotlivé kroky pipeline</CardDescription></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => job("analyze_batch", "Analýzy", { limit: 10 })}>Analyzovat 10 webů</Button>
            <Button size="sm" variant="outline" onClick={() => job("prepare_messages", "Zprávy")}>Připravit zprávy</Button>
            <Button size="sm" variant="outline" onClick={() => job("score_all", "Přepočet")}>Přepočítat skóre</Button>
            <Button size="sm" variant="outline" onClick={() => job("daily_report", "Přehled")}>Denní přehled</Button>
            <Button size="sm" variant="outline" onClick={() => job("check_sources", "Zdroje")}>Zkontrolovat zdroje</Button>
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader className="flex-row items-center justify-between">
          <div>
            <CardTitle>Úlohy</CardTitle>
            <CardDescription>Za 24 h: {Object.entries(st?.last_24h ?? {}).map(([k, v]) => `${JOB_STATUS[k]?.label ?? k} ${v}`).join(" · ") || "—"}</CardDescription>
          </div>
          <div className="flex gap-2">
            <NativeSelect className="w-44" value={filter} onChange={(e) => setFilter(e.target.value)}>
              <option value="">Všechny stavy</option>
              <option value="queued,running">Aktivní</option>
              <option value="failed">Selhané</option>
              <option value="done">Hotové</option>
            </NativeSelect>
            <Button size="icon" variant="outline" onClick={() => mutate()}><RefreshCw /></Button>
          </div>
        </CardHeader>
        {isLoading ? <Skeleton className="m-5 h-64" /> : (
          <Table>
            <THead><TR><TH>#</TH><TH>Úloha</TH><TH>Stav</TH><TH>Spuštění</TH><TH>Pokusy</TH><TH>Vytvořeno</TH><TH>Výsledek</TH><TH /></TR></THead>
            <TBody>
              {jobs?.map((j) => (
                <Fragment key={j.id}>
                  <TR className="cursor-pointer" onClick={() => setOpen(open === j.id ? null : j.id)}>
                    <TD className="text-xs text-muted-foreground">{j.id}{j.parent_id ? ` ← ${j.parent_id}` : ""}</TD>
                    <TD className="font-medium">{meta?.job_types[j.job_type] ?? j.label}{j.payload?.company_id ? <span className="text-xs text-muted-foreground"> · firma {String(j.payload.company_id)}</span> : null}</TD>
                    <TD><Badge variant={JOB_STATUS[j.status]?.variant ?? "muted"}>{JOB_STATUS[j.status]?.label ?? j.status}</Badge></TD>
                    <TD className="text-xs">{j.trigger === "scheduler" ? "plánovač" : j.trigger === "manual" ? "ručně" : j.trigger}</TD>
                    <TD className="text-xs tabular-nums">{j.attempts}/{j.max_attempts}</TD>
                    <TD className="text-xs text-muted-foreground whitespace-nowrap">{fmtRelative(j.created_at)}</TD>
                    <TD className="max-w-md truncate text-xs">{summary(j)}</TD>
                    <TD onClick={(e) => e.stopPropagation()}>
                      {(j.status === "failed" || j.status === "cancelled") && <Button size="icon" variant="ghost" title="Opakovat" onClick={() => act(`/jobs/${j.id}/retry`, "Úloha znovu zařazena")}><RotateCcw /></Button>}
                      {j.status === "queued" && <Button size="icon" variant="ghost" title="Zrušit" onClick={() => act(`/jobs/${j.id}/cancel`, "Úloha zrušena")}><X /></Button>}
                    </TD>
                  </TR>
                  {open === j.id && (
                    <TR>
                      <TD colSpan={8} className="bg-muted/40">
                        <div className="grid gap-3 text-xs md:grid-cols-2">
                          <div>
                            <p className="font-medium">Log</p>
                            {j.log.length ? j.log.map((l, i) => <p key={i}><span className="text-muted-foreground">{l.t.slice(11)}</span> {l.m}</p>) : <p className="text-muted-foreground">—</p>}
                            {j.last_error && <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-red-600">{j.last_error}</pre>}
                          </div>
                          <pre className="max-h-60 overflow-auto rounded bg-card p-2 scrollbar-thin">{JSON.stringify({ payload: j.payload, result: j.result }, null, 2)}</pre>
                        </div>
                      </TD>
                    </TR>
                  )}
                </Fragment>
              ))}
            </TBody>
          </Table>
        )}
      </Card>
    </div>
  );
}
