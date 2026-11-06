"use client";
import { useState } from "react";
import { toast } from "sonner";
import { Plus } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState, Progress } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { useMeta } from "@/components/meta-provider";
import { patch, post, useApi } from "@/lib/api";

type Campaign = { id: number; name: string; description: string | null; segment_keys: string[]; region_codes: string[]; default_strategy: string | null; active: boolean; companies: number; contacted: number; replied: number };

export default function CampaignsPage() {
  const meta = useMeta();
  const { data, mutate } = useApi<Campaign[]>("/campaigns");
  const [form, setForm] = useState({ name: "", description: "", segment_keys: [] as string[], region_codes: [] as string[], default_strategy: "" });

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await post("/campaigns", { ...form, default_strategy: form.default_strategy || null });
      toast.success("Kampaň vytvořena a přiřazeny odpovídající firmy");
      setForm({ name: "", description: "", segment_keys: [], region_codes: [], default_strategy: "" });
      mutate();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }
  return (
    <div>
      <PageHeader title="Kampaně" description="Seskupení leadů podle segmentu a regionu pro měření výsledků." />
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-3">
          {!data?.length && <EmptyState title="Zatím žádné kampaně" description="Vytvořte kampaň – automaticky se do ní zařadí neoslovené firmy z vybraných segmentů a regionů." />}
          {data?.map((c) => (
            <Card key={c.id}>
              <CardContent className="space-y-2 p-5">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{c.name}</p>
                  <label className="flex items-center gap-2 text-xs">
                    {c.active ? "aktivní" : "neaktivní"}
                    <Switch checked={c.active} onCheckedChange={async (v) => { await patch(`/campaigns/${c.id}`, { ...c, active: v }); mutate(); }} />
                  </label>
                </div>
                {c.description && <p className="text-sm text-muted-foreground">{c.description}</p>}
                <div className="flex flex-wrap gap-1">
                  {c.segment_keys.map((k) => <Badge key={k} variant="secondary">{meta?.segments.find((s) => s.key === k)?.label ?? k}</Badge>)}
                  {c.region_codes.map((k) => <Badge key={k} variant="outline">{meta?.regions.find((r) => r.code === k)?.name ?? k}</Badge>)}
                  {c.default_strategy && <Badge variant="info">Strategie {c.default_strategy}</Badge>}
                </div>
                <div className="grid grid-cols-3 gap-3 text-xs">
                  <div><p className="text-muted-foreground">Firem</p><p className="text-lg font-semibold">{c.companies}</p></div>
                  <div><p className="text-muted-foreground">Osloveno</p><p className="text-lg font-semibold">{c.contacted}</p><Progress value={c.companies ? (c.contacted / c.companies) * 100 : 0} /></div>
                  <div><p className="text-muted-foreground">Odpovědi</p><p className="text-lg font-semibold">{c.replied}</p><Progress tone="bg-emerald-500" value={c.contacted ? (c.replied / c.contacted) * 100 : 0} /></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
        <Card>
          <CardHeader><CardTitle>Nová kampaň</CardTitle><CardDescription>Ctrl/Cmd + klik pro výběr více položek</CardDescription></CardHeader>
          <CardContent>
            <form onSubmit={create} className="space-y-3">
              <div className="space-y-1"><Label>Název</Label><Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
              <div className="space-y-1"><Label>Popis</Label><Textarea rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
              <div className="space-y-1">
                <Label>Segmenty</Label>
                <select multiple className="h-36 w-full rounded-md border bg-card p-1 text-sm" value={form.segment_keys}
                  onChange={(e) => setForm({ ...form, segment_keys: Array.from(e.target.selectedOptions).map((o) => o.value) })}>
                  {meta?.segments.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <Label>Regiony</Label>
                <select multiple className="h-28 w-full rounded-md border bg-card p-1 text-sm" value={form.region_codes}
                  onChange={(e) => setForm({ ...form, region_codes: Array.from(e.target.selectedOptions).map((o) => o.value) })}>
                  {meta?.regions.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <Label>Výchozí strategie</Label>
                <NativeSelect value={form.default_strategy} onChange={(e) => setForm({ ...form, default_strategy: e.target.value })}>
                  <option value="">Automaticky</option>
                  {meta && Object.entries(meta.strategies).map(([k, v]) => <option key={k} value={k}>{k} – {v}</option>)}
                </NativeSelect>
              </div>
              <Button type="submit"><Plus /> Vytvořit</Button>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
