"use client";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { Loader2, Plus, Search, Upload } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useMeta } from "@/components/meta-provider";
import { AddCompanyDialog } from "@/components/add-company-dialog";
import { post, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";

type Source = {
  key: string; name: string; kind: string; access_policy: string; configured: boolean; supports_discovery: boolean;
  enabled: boolean; last_status: string | null; last_error: string | null; last_check_at: string | null;
  total_requests: number; total_errors: number; total_records: number;
};
type Stats = { found: number; created: number; updated: number; skipped: number; suppressed: number; errors: string[]; sources_used: string[] };

const STATUS: Record<string, "success" | "danger" | "warning" | "muted"> = { ok: "success", unavailable: "danger", error: "danger", not_configured: "warning" };

export default function DiscoveryPage() {
  const meta = useMeta();
  const { data: sources, mutate: mutateSources } = useApi<Source[]>("/sources");
  const [form, setForm] = useState({ segment_key: "interior_design", region_code: "CZ-10", city: "", country: "CZ", keyword: "", limit: 40, require_website: true, auto_analyze: true, auto_analyze_limit: 15 });
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Stats | null>(null);
  const [checking, setChecking] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function run(sync: boolean) {
    setRunning(true);
    setResult(null);
    try {
      const body = { ...form, segment_key: form.segment_key || null, region_code: form.city ? null : form.region_code || null, city: form.city || null,
        keyword: form.keyword || null, sources: selectedSources.length ? selectedSources : null, sync };
      if (sync) {
        const r = await post<Stats>("/discovery/run", body);
        setResult(r);
        toast.success(`Nalezeno ${r.found}, nových ${r.created}`);
      } else {
        const r = await post<{ job_id: number }>("/discovery/run", body);
        toast.success(`Vyhledávání zařazeno do fronty (úloha #${r.job_id})`);
      }
      mutateSources();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setRunning(false);
    }
  }
  async function check() {
    setChecking(true);
    try {
      await post("/sources/check");
      await mutateSources();
    } finally {
      setChecking(false);
    }
  }
  async function upload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const res = await fetch(`/api/companies/import?analyze=true`, { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Import selhal");
      toast.success(`Import: ${data.created} nových, ${data.updated} aktualizováno, ${data.skipped} přeskočeno`);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  return (
    <div>
      <PageHeader title="Vyhledávání firem" description="Automatický discovery engine nad legálními zdroji. Výsledky se deduplikují a ukládají do CRM."
        actions={<Button variant="outline" onClick={() => setAddOpen(true)}><Plus /> Přidat ručně</Button>} />
      <AddCompanyDialog open={addOpen} onOpenChange={setAddOpen} />

      <div className="grid gap-6 lg:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader>
            <CardTitle>Nové vyhledávání</CardTitle>
            <CardDescription>Hledejte podle oboru a kraje / města, případně podle klíčového slova v názvu.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label>Obor</Label>
                <NativeSelect value={form.segment_key} onChange={(e) => setForm({ ...form, segment_key: e.target.value })}>
                  <option value="">— jen klíčové slovo —</option>
                  {[1, 2, 3].map((t) => (
                    <optgroup key={t} label={meta?.tiers[String(t)] ?? `Tier ${t}`}>
                      {meta?.segments.filter((s) => s.tier === t).map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
                    </optgroup>
                  ))}
                </NativeSelect>
              </div>
              <div className="space-y-1">
                <Label>Kraj</Label>
                <NativeSelect value={form.region_code} disabled={!!form.city} onChange={(e) => setForm({ ...form, region_code: e.target.value })}>
                  <option value="">Celá země</option>
                  {meta?.regions.map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}
                </NativeSelect>
              </div>
              <div className="space-y-1">
                <Label>Město (přepíše kraj)</Label>
                <Input placeholder="např. Brno, Wien, München" value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>Země (ISO kód – pro zahraniční klienty)</Label>
                <Input maxLength={2} value={form.country} onChange={(e) => setForm({ ...form, country: e.target.value.toUpperCase() })} />
              </div>
              <div className="space-y-1">
                <Label>Klíčové slovo v názvu (volitelné)</Label>
                <Input placeholder="např. ateliér" value={form.keyword} onChange={(e) => setForm({ ...form, keyword: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label>Max. výsledků</Label>
                <Input type="number" min={1} max={300} value={form.limit} onChange={(e) => setForm({ ...form, limit: Number(e.target.value) })} />
              </div>
            </div>
            <div className="space-y-1">
              <Label>Zdroje (prázdné = všechny dostupné)</Label>
              <div className="flex flex-wrap gap-2">
                {sources?.filter((s) => s.supports_discovery).map((s) => (
                  <label key={s.key} className="flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs">
                    <input type="checkbox" disabled={!s.configured} checked={selectedSources.includes(s.key)}
                      onChange={(e) => setSelectedSources(e.target.checked ? [...selectedSources, s.key] : selectedSources.filter((k) => k !== s.key))} />
                    {s.name}{!s.configured && " (nenastaveno)"}
                  </label>
                ))}
              </div>
            </div>
            <div className="flex flex-wrap gap-6 text-sm">
              <label className="flex items-center gap-2"><Switch checked={form.require_website} onCheckedChange={(v) => setForm({ ...form, require_website: v })} /> Jen firmy s webem</label>
              <label className="flex items-center gap-2"><Switch checked={form.auto_analyze} onCheckedChange={(v) => setForm({ ...form, auto_analyze: v })} /> Rovnou analyzovat (max. {form.auto_analyze_limit})</label>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => run(false)} disabled={running}>{running ? <Loader2 className="animate-spin" /> : <Search />} Spustit na pozadí</Button>
              <Button variant="outline" onClick={() => run(true)} disabled={running}>Spustit a počkat na výsledek</Button>
            </div>
            {result && (
              <div className="rounded-lg border bg-muted/40 p-3 text-sm">
                <p>Nalezeno <b>{result.found}</b> · nových <b>{result.created}</b> · aktualizováno {result.updated} · přeskočeno {result.skipped}{result.suppressed ? ` · na DNC ${result.suppressed}` : ""}</p>
                {result.errors.map((e, i) => <p key={i} className="text-xs text-red-600">{e}</p>)}
                <Link href="/leady?sort=newest" className="text-xs text-primary underline">Zobrazit nejnovější leady</Link>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle>Zdroje dat</CardTitle>
              <Button size="sm" variant="outline" onClick={check} disabled={checking}>{checking ? <Loader2 className="animate-spin" /> : null} Zkontrolovat dostupnost</Button>
            </CardHeader>
            <CardContent className="space-y-3">
              {sources?.map((s) => (
                <div key={s.key} className="rounded-lg border p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">{s.name}</p>
                    <Badge variant={STATUS[s.last_status ?? ""] ?? "muted"}>{s.last_status ?? "neověřeno"}</Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-muted-foreground">{s.access_policy}</p>
                  <p className="mt-1 text-[11px] text-muted-foreground">
                    Požadavků {s.total_requests} · záznamů {s.total_records} · chyb {s.total_errors}{s.last_check_at ? ` · ${fmtDate(s.last_check_at, true)}` : ""}
                  </p>
                  {s.last_error && <p className="mt-1 line-clamp-2 text-[11px] text-red-600">{s.last_error}</p>}
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Import z CSV</CardTitle>
              <CardDescription>Sloupce: name, website, city, ico, email, phone, segment_key (oddělovač , nebo ;)</CardDescription>
            </CardHeader>
            <CardContent>
              <label className="flex cursor-pointer items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-sm hover:bg-muted">
                {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Vybrat soubor CSV
                <input type="file" accept=".csv,text/csv" className="hidden" onChange={upload} />
              </label>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
