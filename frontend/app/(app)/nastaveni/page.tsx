"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Cpu, Save, TrendingUp } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton, Table, TBody, TD, TH, THead, TR } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMeta } from "@/components/meta-provider";
import { post, put, useApi } from "@/lib/api";

/* eslint-disable @typescript-eslint/no-explicit-any */
type Settings = Record<string, any>;
type AiStatus = {
  text: { available: boolean; provider: string | null; model: string | null; note: string };
  vision: { available: boolean; provider: string | null; model: string | null; note: string };
  playwright: { available: boolean; note: string };
  hardware: { ram_gb: number | null; cpu_count: number; nvidia_gpu: boolean; recommendation: string };
};
type Learning = {
  strategies: Record<string, { label: string; sent: number; replied: number; positive: number; reply_rate: number; positive_rate: number; raw_reply_rate: number | null }>;
  segments: { segment_key: string; label: string; sent: number; replied: number; positive: number; reply_rate: number }[];
  suggestions: { segment_key: string; label: string; current: number; suggested: number; reason: string }[];
};

const WEIGHT_LABELS: Record<string, string> = {
  design_gap: "Design Gap", commercial_potential: "Commercial Potential", buying_readiness: "Buying Readiness",
  service_fit: "Service Fit", contactability: "Contactability",
};

function NumberField({ label, value, onChange, step = 1, min, max, suffix }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number; suffix?: string }) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      <div className="flex items-center gap-2">
        <Input type="number" step={step} min={min} max={max} value={value ?? ""} onChange={(e) => onChange(e.target.value === "" ? 0 : Number(e.target.value))} />
        {suffix && <span className="text-xs text-muted-foreground">{suffix}</span>}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const meta = useMeta();
  const { data, mutate } = useApi<Settings>("/settings");
  const { data: ai } = useApi<AiStatus>("/ai/status");
  const { data: learning, mutate: mutateLearning } = useApi<Learning>("/learning");
  const [s, setS] = useState<Settings | null>(null);
  useEffect(() => { if (data) setS(structuredClone(data)); }, [data]);

  async function save(key: string) {
    if (!s) return;
    try {
      await put(`/settings/${key}`, s[key]);
      toast.success("Nastavení uloženo");
      mutate();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  if (!s) return <Skeleton className="h-[600px]" />;
  const set = (key: string, path: string[], value: unknown) => {
    const next = structuredClone(s);
    let o = next[key];
    for (const p of path.slice(0, -1)) o = o[p];
    o[path[path.length - 1]] = value;
    setS(next);
  };
  const weightSum = Object.values(s.scoring.weights as Record<string, number>).reduce((a, b) => a + Number(b), 0);

  return (
    <div>
      <PageHeader title="Nastavení" description="Cíle automatizace, scoring, ceny, priority segmentů a regionů, AI a učení z výsledků." />
      <Tabs defaultValue="automation">
        <TabsList>
          <TabsTrigger value="automation">Automatizace</TabsTrigger>
          <TabsTrigger value="scoring">Scoring</TabsTrigger>
          <TabsTrigger value="pricing">Ceny</TabsTrigger>
          <TabsTrigger value="segments">Segmenty</TabsTrigger>
          <TabsTrigger value="regions">Regiony</TabsTrigger>
          <TabsTrigger value="messages">Zprávy & agentura</TabsTrigger>
          <TabsTrigger value="learning">Výsledky & učení</TabsTrigger>
          <TabsTrigger value="ai">AI & systém</TabsTrigger>
        </TabsList>

        <TabsContent value="automation">
          <Card>
            <CardHeader><CardTitle>Denní cíle a plán</CardTitle><CardDescription>Cíle jsou maxima – skutečné objemy závisí na dostupnosti zdrojů a kvalitě nalezených firem.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <NumberField label="Objevit až (firem/den)" value={s.automation.daily_discovery_target} onChange={(v) => set("automation", ["daily_discovery_target"], v)} />
              <NumberField label="Analyzovat až (webů/den)" value={s.automation.daily_analysis_target} onChange={(v) => set("automation", ["daily_analysis_target"], v)} />
              <NumberField label="Připravit až (zpráv/den)" value={s.automation.daily_message_target} onChange={(v) => set("automation", ["daily_message_target"], v)} />
              <NumberField label="Min. skóre pro zprávu" value={s.automation.min_score_for_messages} onChange={(v) => set("automation", ["min_score_for_messages"], v)} />
              <NumberField label="Hodina denního běhu" min={0} max={23} value={s.automation.daily_run_hour} onChange={(v) => set("automation", ["daily_run_hour"], v)} />
              <NumberField label="Minuta" min={0} max={59} value={s.automation.daily_run_minute} onChange={(v) => set("automation", ["daily_run_minute"], v)} />
              <NumberField label="Znovu analyzovat po" value={s.automation.reanalyze_after_days} onChange={(v) => set("automation", ["reanalyze_after_days"], v)} suffix="dnech" />
              <div className="space-y-1">
                <Label>Pozastaveno</Label>
                <div className="pt-2"><Switch checked={!!s.automation.paused} onCheckedChange={(v) => set("automation", ["paused"], v)} /></div>
              </div>
            </CardContent>
            <CardContent className="grid gap-4 border-t pt-5 sm:grid-cols-2 lg:grid-cols-4">
              <NumberField label="1. follow-up po" value={s.followup.first_followup_days} onChange={(v) => set("followup", ["first_followup_days"], v)} suffix="dnech" />
              <NumberField label="2. follow-up po" value={s.followup.second_followup_days} onChange={(v) => set("followup", ["second_followup_days"], v)} suffix="dnech" />
              <NumberField label="Max. follow-upů" value={s.followup.max_followups} onChange={(v) => set("followup", ["max_followups"], v)} />
              <NumberField label="Kontrola spojení po" value={s.followup.connection_check_days} onChange={(v) => set("followup", ["connection_check_days"], v)} suffix="dnech" />
            </CardContent>
            <CardContent className="flex gap-2">
              <Button onClick={() => save("automation")}><Save /> Uložit automatizaci</Button>
              <Button variant="outline" onClick={() => save("followup")}><Save /> Uložit follow-upy</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="scoring">
          <Card>
            <CardHeader><CardTitle>Váhy Opportunity Score</CardTitle><CardDescription>Součet musí být 100 %. Po uložení se všechna skóre přepočítají.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {Object.entries(s.scoring.weights as Record<string, number>).map(([k, v]) => (
                <NumberField key={k} label={WEIGHT_LABELS[k] ?? k} step={5} value={Math.round(Number(v) * 100)} onChange={(x) => set("scoring", ["weights", k], x / 100)} suffix="%" />
              ))}
            </CardContent>
            <CardContent className="grid gap-4 border-t pt-5 sm:grid-cols-3">
              <NumberField label="Min. podíl známých vah" step={5} value={Math.round(s.scoring.min_known_weight * 100)} onChange={(v) => set("scoring", ["min_known_weight"], v / 100)} suffix="%" />
              <NumberField label="„Již kvalitní web“ od Visual Score" value={s.scoring.already_good_visual_score} onChange={(v) => set("scoring", ["already_good_visual_score"], v)} />
              <NumberField label="Nízký ekonomický potenciál pod" value={s.scoring.low_commercial_threshold} onChange={(v) => set("scoring", ["low_commercial_threshold"], v)} />
            </CardContent>
            <CardContent className="flex items-center gap-3">
              <Button onClick={() => save("scoring")} disabled={Math.abs(weightSum - 1) > 0.02}><Save /> Uložit a přepočítat</Button>
              <span className={Math.abs(weightSum - 1) > 0.02 ? "text-sm text-red-600" : "text-sm text-muted-foreground"}>Součet vah: {Math.round(weightSum * 100)} %</span>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pricing">
          <Card>
            <CardHeader><CardTitle>Cenové segmenty Project Two</CardTitle><CardDescription>Používají se pro odhad vhodné nabídky. Nejde o rozpočet klienta.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              {Object.entries(s.pricing as Record<string, { label: string; min: number; max: number | null }>).map(([k, p]) => (
                <div key={k} className="grid items-end gap-3 sm:grid-cols-[1fr_160px_160px]">
                  <div className="space-y-1"><Label>Služba</Label><Input value={p.label} onChange={(e) => set("pricing", [k, "label"], e.target.value)} /></div>
                  <NumberField label="Od (Kč)" step={1000} value={p.min} onChange={(v) => set("pricing", [k, "min"], v)} />
                  <NumberField label="Do (Kč, 0 = bez limitu)" step={1000} value={p.max ?? 0} onChange={(v) => set("pricing", [k, "max"], v || null)} />
                </div>
              ))}
              <Button onClick={() => save("pricing")}><Save /> Uložit ceny</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="segments">
          <Card>
            <CardHeader><CardTitle>Priority segmentů</CardTitle><CardDescription>Výchozí tiery jsou hypotézy. Multiplikátor upravuje Service Fit i pořadí vyhledávání. Návrhy podle výsledků najdete v záložce Výsledky & učení.</CardDescription></CardHeader>
            <Table>
              <THead><TR><TH>Segment</TH><TH>Tier</TH><TH>Aktivní</TH><TH>Multiplikátor</TH></TR></THead>
              <TBody>
                {meta?.segments.map((seg) => {
                  const cfg = s.segment_priorities[seg.key] ?? { enabled: true, multiplier: 1 };
                  return (
                    <TR key={seg.key}>
                      <TD>{seg.label}</TD>
                      <TD><Badge variant="outline">Tier {seg.tier}</Badge></TD>
                      <TD><Switch checked={cfg.enabled} onCheckedChange={(v) => set("segment_priorities", [seg.key], { ...cfg, enabled: v })} /></TD>
                      <TD className="w-40"><Input type="number" step={0.05} min={0.3} max={2} value={cfg.multiplier} onChange={(e) => set("segment_priorities", [seg.key], { ...cfg, multiplier: Number(e.target.value) })} /></TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
            <CardContent className="pt-4"><Button onClick={() => save("segment_priorities")}><Save /> Uložit a přepočítat</Button></CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="regions">
          <Card>
            <CardHeader><CardTitle>Regiony</CardTitle><CardDescription>Priorita 1–5 určuje pořadí automatického vyhledávání. Slovensko je ve výchozím stavu vypnuté.</CardDescription></CardHeader>
            <Table>
              <THead><TR><TH>Kraj</TH><TH>Země</TH><TH>Aktivní</TH><TH>Priorita</TH></TR></THead>
              <TBody>
                {meta?.regions.map((r) => {
                  const cfg = s.region_priorities[r.code] ?? { enabled: false, priority: r.default_priority };
                  return (
                    <TR key={r.code}>
                      <TD>{r.name}</TD>
                      <TD>{r.country}</TD>
                      <TD><Switch checked={cfg.enabled} onCheckedChange={(v) => set("region_priorities", [r.code], { ...cfg, enabled: v })} /></TD>
                      <TD className="w-32"><Input type="number" min={1} max={5} value={cfg.priority} onChange={(e) => set("region_priorities", [r.code], { ...cfg, priority: Number(e.target.value) })} /></TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
            <CardContent className="pt-4"><Button onClick={() => save("region_priorities")}><Save /> Uložit regiony</Button></CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="messages">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>Zprávy</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1"><Label>Podpis (jméno odesílatele)</Label><Input value={s.messages.sender_name} onChange={(e) => set("messages", ["sender_name"], e.target.value)} /></div>
                <NumberField label="Max. znaků žádosti o spojení" value={s.messages.connection_request_max_chars} onChange={(v) => set("messages", ["connection_request_max_chars"], v)} />
                <NumberField label="Max. znaků první zprávy" value={s.messages.first_message_max_chars} onChange={(v) => set("messages", ["first_message_max_chars"], v)} />
                <Button onClick={() => save("messages")}><Save /> Uložit</Button>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>O agentuře (fakta pro zprávy)</CardTitle><CardDescription>Model smí používat jen tato fakta o Project Two.</CardDescription></CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-1"><Label>Fakta (1 řádek = 1 fakt)</Label>
                  <Textarea rows={5} value={(s.agency.facts as string[]).join("\n")} onChange={(e) => set("agency", ["facts"], e.target.value.split("\n").filter(Boolean))} />
                </div>
                <div className="space-y-1"><Label>Reference (název | URL | klíč segmentu)</Label>
                  <Textarea rows={4} value={(s.agency.portfolio as { name: string; url: string; segment: string }[]).map((p) => `${p.name} | ${p.url} | ${p.segment}`).join("\n")}
                    onChange={(e) => set("agency", ["portfolio"], e.target.value.split("\n").filter(Boolean).map((l) => { const [name, url, segment] = l.split("|").map((x) => x.trim()); return { name, url, segment }; }))} />
                </div>
                <Button onClick={() => save("agency")}><Save /> Uložit</Button>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="learning">
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>A/B strategie zpráv</CardTitle><CardDescription>Míry jsou Bayesovsky vyhlazené – malý počet zpráv neurčuje vítěze.</CardDescription></CardHeader>
              <Table>
                <THead><TR><TH>Strategie</TH><TH>Odesláno</TH><TH>Odpovědi</TH><TH>Kladné</TH><TH>Odhad míry odpovědí</TH></TR></THead>
                <TBody>
                  {learning && Object.entries(learning.strategies).map(([k, v]) => (
                    <TR key={k}><TD><b>{k}</b> – {v.label}</TD><TD>{v.sent}</TD><TD>{v.replied}</TD><TD>{v.positive}</TD><TD>{Math.round(v.reply_rate * 100)} %</TD></TR>
                  ))}
                </TBody>
              </Table>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2"><TrendingUp className="h-4 w-4" /> Výkon segmentů</CardTitle></CardHeader>
              <Table>
                <THead><TR><TH>Segment</TH><TH>Osloveno</TH><TH>Odpovědi</TH><TH>Schůzky/klienti</TH></TR></THead>
                <TBody>
                  {learning?.segments.map((x) => <TR key={x.segment_key}><TD>{x.label}</TD><TD>{x.sent}</TD><TD>{x.replied}</TD><TD>{x.positive}</TD></TR>)}
                  {!learning?.segments.length && <TR><TD colSpan={4} className="text-muted-foreground">Zatím žádná oslovení.</TD></TR>}
                </TBody>
              </Table>
              <CardContent className="space-y-2 pt-4">
                <p className="text-sm font-medium">Návrhy úprav priorit</p>
                {learning?.suggestions.length ? learning.suggestions.map((x) => (
                  <p key={x.segment_key} className="text-sm">{x.label}: ×{x.current} → <b>×{x.suggested}</b> <span className="text-xs text-muted-foreground">({x.reason})</span></p>
                )) : <p className="text-sm text-muted-foreground">Pro návrh je potřeba alespoň 5 oslovení v segmentu.</p>}
                {!!learning?.suggestions.length && (
                  <Button size="sm" onClick={async () => { await post("/learning/apply"); toast.success("Priority upraveny"); mutateLearning(); mutate(); }}><Check /> Použít návrhy</Button>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="ai">
          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2"><Cpu className="h-4 w-4" /> AI a prohlížeč</CardTitle><CardDescription>Konfigurace se nastavuje v backend/.env (TEXT_PROVIDER, VISION_PROVIDER, OLLAMA_*, ANTHROPIC_API_KEY…).</CardDescription></CardHeader>
            <CardContent className="space-y-3 text-sm">
              {ai ? (
                <>
                  {([["Textový model", ai.text], ["Vision model", ai.vision]] as const).map(([label, x]) => (
                    <div key={label} className="flex flex-wrap items-center gap-2">
                      <span className="w-32 font-medium">{label}</span>
                      {x.available ? <Badge variant="success">{x.provider} · {x.model}</Badge> : <Badge variant="danger">nedostupný</Badge>}
                      <span className="text-xs text-muted-foreground">{x.note}</span>
                    </div>
                  ))}
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="w-32 font-medium">Playwright</span>
                    {ai.playwright.available ? <Badge variant="success">OK</Badge> : <Badge variant="danger">nedostupný</Badge>}
                    <span className="text-xs text-muted-foreground">{ai.playwright.note}</span>
                  </div>
                  <div className="rounded-md bg-muted p-3 text-xs">
                    <p>RAM {ai.hardware.ram_gb ?? "?"} GB · CPU {ai.hardware.cpu_count} · GPU {ai.hardware.nvidia_gpu ? "ano" : "ne"}</p>
                    <p className="mt-1">{ai.hardware.recommendation}</p>
                  </div>
                </>
              ) : <Skeleton className="h-24" />}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
