"use client";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle, Check, Copy, Loader2, Save, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { NativeSelect, Textarea } from "@/components/ui/input";
import { useMeta } from "@/components/meta-provider";
import { patch, post } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Message } from "@/lib/types";

export const TYPE_ORDER = ["connection_request", "first_message", "follow_up", "alternative", "pitch"];

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

export function MessagesPanel({
  companyId,
  messages,
  onChanged,
  activeType,
  onActiveTypeChange,
  compact = false,
}: {
  companyId: number;
  messages: Message[];
  onChanged: () => void;
  activeType?: string;
  onActiveTypeChange?: (t: string) => void;
  compact?: boolean;
}) {
  const meta = useMeta();
  const drafts = messages.filter((m) => m.status === "draft");
  const sent = messages.filter((m) => m.status === "sent");
  const [strategy, setStrategy] = useState("auto");
  const [generating, setGenerating] = useState(false);
  const [localType, setLocalType] = useState("connection_request");
  const type = activeType ?? localType;
  const setType = onActiveTypeChange ?? setLocalType;
  const current = drafts.find((m) => m.message_type === type) ?? drafts[0];
  const [text, setText] = useState(current?.content ?? "");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setText(current?.content ?? "");
    setCopied(false);
  }, [current?.id, current?.content]);

  async function generate() {
    setGenerating(true);
    try {
      await post(`/companies/${companyId}/messages/generate`, { strategy });
      toast.success("Zprávy vygenerovány");
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setGenerating(false);
    }
  }
  async function save() {
    if (!current) return;
    await patch(`/messages/${current.id}`, { content: text });
    toast.success("Zpráva uložena");
    onChanged();
  }
  async function copy() {
    if (await copyText(text)) {
      setCopied(true);
      toast.success("Zkopírováno do schránky");
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect className="w-auto" value={strategy} onChange={(e) => setStrategy(e.target.value)} title="Strategie oslovení (A/B test)">
          <option value="auto">Strategie: automaticky</option>
          {meta && Object.entries(meta.strategies).map(([k, v]) => <option key={k} value={k}>{k} – {v}</option>)}
        </NativeSelect>
        <Button size="sm" variant={drafts.length ? "outline" : "default"} onClick={generate} disabled={generating}>
          {generating ? <Loader2 className="animate-spin" /> : <Sparkles />} {drafts.length ? "Přegenerovat" : "Vygenerovat zprávy"}
        </Button>
        {current && (
          <span className="text-xs text-muted-foreground">
            Strategie <b>{current.strategy}</b> – {current.strategy_label} · {current.generator.startsWith("llm") ? "AI model" : "kompozitor z faktů"}
          </span>
        )}
      </div>

      {drafts.length > 0 && (
        <>
          <div className="flex flex-wrap gap-1">
            {TYPE_ORDER.map((t, i) => {
              const m = drafts.find((d) => d.message_type === t);
              if (!m) return null;
              return (
                <button key={t} onClick={() => setType(t)}
                  className={cn("rounded-md border px-2.5 py-1 text-xs cursor-pointer", t === type ? "border-primary bg-accent font-medium" : "hover:bg-muted")}>
                  <kbd className="mr-1">{i + 1}</kbd>{meta?.message_types[t] ?? t}
                  {m.quality_warnings.length > 0 && <AlertTriangle className="ml-1 inline h-3 w-3 text-amber-500" />}
                </button>
              );
            })}
          </div>
          {current && (
            <div className="space-y-2">
              <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={compact ? 8 : 10} className="font-[450] leading-relaxed" />
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className={cn("text-xs", type === "connection_request" && text.length > 300 ? "text-red-600" : "text-muted-foreground")}>
                  {text.length} znaků{type === "connection_request" && " (LinkedIn limit poznámky 300, bez Premium 200)"}
                </span>
                <div className="flex gap-2">
                  {text !== current.content && <Button size="sm" variant="outline" onClick={save}><Save /> Uložit úpravu</Button>}
                  <Button size="sm" onClick={copy}>{copied ? <Check /> : <Copy />} Kopírovat <kbd className="bg-transparent text-inherit border-white/40">C</kbd></Button>
                </div>
              </div>
              {current.quality_warnings.length > 0 && (
                <div className="rounded-md bg-amber-50 p-2 text-xs text-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
                  {current.quality_warnings.map((w, i) => <p key={i}>⚠ {w}</p>)}
                </div>
              )}
              {!compact && (
                <details className="text-xs text-muted-foreground">
                  <summary className="cursor-pointer">Použitá fakta ({current.facts_used.length})</summary>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">
                    {current.facts_used.map((f, i) => <li key={i}><b>{f.key}</b>: {f.text} <i>({f.source})</i></li>)}
                  </ul>
                </details>
              )}
            </div>
          )}
        </>
      )}
      {drafts.length === 0 && <p className="text-sm text-muted-foreground">Zatím žádné připravené zprávy.</p>}
      {!compact && sent.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Odeslané zprávy</p>
          {sent.map((m) => (
            <div key={m.id} className="rounded-md border p-2 text-xs">
              <div className="mb-1 flex gap-2">
                <Badge variant="secondary">{m.message_type_label}</Badge>
                <Badge variant="outline">Strategie {m.strategy}</Badge>
                <Badge variant={m.outcome.startsWith("replied_positive") || m.outcome === "meeting" || m.outcome === "won" ? "success" : m.outcome === "replied_negative" ? "danger" : "muted"}>{m.outcome}</Badge>
              </div>
              <p className="whitespace-pre-wrap text-muted-foreground">{m.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
