"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Check, Linkedin, Send, X } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ReplyDialog } from "@/components/lead/outreach-actions";
import { patch, post, useApi } from "@/lib/api";
import { fmtDate, fmtRelative } from "@/lib/format";
import type { Task } from "@/lib/types";

const TYPE_LABEL: Record<string, string> = {
  follow_up: "Follow-up",
  check_connection: "Kontrola spojení",
  custom: "Úkol",
  call: "Hovor",
};

export default function FollowUpPage() {
  const [scope, setScope] = useState("due");
  const { data, mutate, isLoading } = useApi<Task[]>(`/tasks?scope=${scope}`, { refreshInterval: 30000 });
  const [replyFor, setReplyFor] = useState<number | null>(null);

  async function complete(t: Task, sent: boolean) {
    try {
      const r = await post<{ next_task: Task | null }>(`/tasks/${t.id}/complete`, { sent });
      toast.success(sent ? (r.next_task ? `Odesláno – další připomínka ${fmtDate(r.next_task.due_at)}` : "Odesláno – limit follow-upů vyčerpán") : "Úkol dokončen");
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function connected(t: Task) {
    if (!t.contact_id) return complete(t, false);
    await patch(`/contacts/${t.contact_id}`, { connection_status: "connected" });
    toast.success("Spojení přijato – naplánováno odeslání první zprávy");
    mutate();
  }
  async function cancel(t: Task) {
    await patch(`/tasks/${t.id}`, { status: "cancelled" });
    mutate();
  }

  return (
    <div>
      <PageHeader title="Follow-upy" description="Připomínky se po odpovědi nebo odmítnutí automaticky zastaví. Nic se neodesílá automaticky." />
      <Tabs value={scope} onValueChange={setScope} className="mb-4">
        <TabsList>
          <TabsTrigger value="due">Dnes a po termínu</TabsTrigger>
          <TabsTrigger value="upcoming">Nadcházející</TabsTrigger>
          <TabsTrigger value="open">Všechny otevřené</TabsTrigger>
          <TabsTrigger value="done">Hotové / zrušené</TabsTrigger>
        </TabsList>
      </Tabs>
      {isLoading ? <Skeleton className="h-64" /> : !data?.length ? (
        <EmptyState title="Žádné úkoly" description={scope === "due" ? "Na dnešek nic nečeká. 🎉" : "V této kategorii nejsou žádné úkoly."} />
      ) : (
        <Card className="divide-y">
          {data.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center gap-3 p-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={t.overdue ? "danger" : "secondary"}>{TYPE_LABEL[t.task_type] ?? t.task_type}</Badge>
                  <Link href={`/leady/${t.company_id}`} className="font-medium hover:underline">{t.company_name}</Link>
                  {t.contact_name && <span className="text-sm text-muted-foreground">· {t.contact_name}</span>}
                </div>
                <p className="mt-0.5 text-sm">{t.title}</p>
                <p className="text-xs text-muted-foreground">
                  {t.status === "open" ? `Termín ${fmtDate(t.due_at, true)} (${fmtRelative(t.due_at)})` : `${t.status === "done" ? "Dokončeno" : "Zrušeno"} ${fmtDate(t.completed_at)}${t.cancelled_reason ? ` – ${t.cancelled_reason}` : ""}`}
                  {t.reason ? ` · ${t.reason}` : ""}
                </p>
              </div>
              {t.status === "open" && (
                <div className="flex flex-wrap gap-2">
                  {t.linkedin_url && (
                    <Button asChild size="sm" variant="outline"><a href={t.linkedin_url} target="_blank" rel="noreferrer"><Linkedin /> LinkedIn</a></Button>
                  )}
                  {t.task_type === "check_connection" && <Button size="sm" variant="outline" onClick={() => connected(t)}><Check /> Spojení přijato</Button>}
                  {t.task_type === "follow_up" && (
                    <Button size="sm" asChild variant="outline"><Link href={`/leady/${t.company_id}`}><Send /> Zpráva</Link></Button>
                  )}
                  {t.task_type === "follow_up" && <Button size="sm" variant="success" onClick={() => complete(t, true)}><Check /> Follow-up odeslán</Button>}
                  {t.task_type !== "follow_up" && t.task_type !== "check_connection" && <Button size="sm" onClick={() => complete(t, false)}><Check /> Hotovo</Button>}
                  <Button size="sm" variant="outline" onClick={() => setReplyFor(t.company_id)}>Odpověděl</Button>
                  <Button size="icon" variant="ghost" onClick={() => cancel(t)} title="Zrušit"><X /></Button>
                </div>
              )}
            </div>
          ))}
        </Card>
      )}
      {replyFor !== null && <ReplyDialog open companyId={replyFor} onOpenChange={(v) => !v && setReplyFor(null)} onDone={mutate} />}
    </div>
  );
}
