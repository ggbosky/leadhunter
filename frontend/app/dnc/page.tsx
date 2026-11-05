"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { EmptyState, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { useMeta } from "@/components/meta-provider";
import { del, post, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type Entry = { id: number; company_id: number | null; domain: string | null; ico: string | null; email: string | null; linkedin_url: string | null; name: string | null; reason: string; note: string | null; created_at: string };

export default function DncPage() {
  const meta = useMeta();
  const { data, mutate } = useApi<Entry[]>("/suppression");
  const [form, setForm] = useState({ domain: "", ico: "", email: "", linkedin_url: "", name: "", reason: "manual", note: "" });
  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await post("/suppression", Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v || null])));
      toast.success("Přidáno na Do Not Contact");
      setForm({ domain: "", ico: "", email: "", linkedin_url: "", name: "", reason: "manual", note: "" });
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }
  async function remove(id: number) {
    if (!confirm("Odebrat ze seznamu Do Not Contact? Firmu bude možné znovu oslovit.")) return;
    await del(`/suppression/${id}`);
    mutate();
  }
  return (
    <div>
      <PageHeader title="Do Not Contact" description="Firmy a osoby, které nesmí být oslovovány. Kontrola probíhá podle IČO, domény, e-mailu i LinkedIn profilu." />
      <Card className="mb-6">
        <CardHeader><CardTitle className="text-base">Přidat ručně</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={add} className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <Input placeholder="Název" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <Input placeholder="Doména (example.cz)" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} />
            <Input placeholder="IČO" value={form.ico} onChange={(e) => setForm({ ...form, ico: e.target.value })} />
            <Input placeholder="E-mail" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            <Input placeholder="LinkedIn URL" value={form.linkedin_url} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })} />
            <NativeSelect value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })}>
              {meta && Object.entries(meta.suppression_reasons).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect>
            <Input placeholder="Poznámka" value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} />
            <Button type="submit">Přidat</Button>
          </form>
        </CardContent>
      </Card>
      {!data?.length ? <EmptyState title="Seznam je prázdný" /> : (
        <Card>
          <Table>
            <THead><TR><TH>Firma / osoba</TH><TH>Identifikátory</TH><TH>Důvod</TH><TH>Přidáno</TH><TH /></TR></THead>
            <TBody>
              {data.map((e) => (
                <TR key={e.id}>
                  <TD>{e.company_id ? <Link className="font-medium hover:underline" href={`/leady/${e.company_id}`}>{e.name}</Link> : e.name ?? "—"}</TD>
                  <TD className="text-xs text-muted-foreground">{[e.domain, e.ico && `IČO ${e.ico}`, e.email, e.linkedin_url].filter(Boolean).join(" · ")}</TD>
                  <TD><Badge variant="danger">{meta?.suppression_reasons[e.reason] ?? e.reason}</Badge>{e.note && <p className="text-xs text-muted-foreground">{e.note}</p>}</TD>
                  <TD className="text-xs">{fmtDate(e.created_at)}</TD>
                  <TD><Button size="icon" variant="ghost" onClick={() => remove(e.id)}><Trash2 /></Button></TD>
                </TR>
              ))}
            </TBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
