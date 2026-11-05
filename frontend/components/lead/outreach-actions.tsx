"use client";
import { useState } from "react";
import { toast } from "sonner";
import { CalendarClock, CheckCheck, MessageSquareReply, ThumbsDown, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { post } from "@/lib/api";

export const OUTCOME_LABELS: Record<string, string> = {
  replied_positive: "Pozitivní odpověď",
  replied_neutral: "Neutrální odpověď",
  replied_negative: "Negativní odpověď",
  meeting: "Domluvená schůzka",
  won: "Získaný klient",
  lost: "Ztraceno",
};

export function ReplyDialog({ open, onOpenChange, companyId, onDone }: { open: boolean; onOpenChange: (v: boolean) => void; companyId: number; onDone: () => void }) {
  const [outcome, setOutcome] = useState("replied_positive");
  const [notes, setNotes] = useState("");
  const [nextStep, setNextStep] = useState("");
  const [nextAt, setNextAt] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await post(`/companies/${companyId}/outreach/reply`, {
        outcome, notes: notes || null, next_step: nextStep || null,
        next_step_at: nextAt ? new Date(nextAt).toISOString() : null,
      });
      toast.success("Odpověď zaznamenána – připomínky zastaveny");
      onOpenChange(false);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Zaznamenat odpověď</DialogTitle>
          <DialogDescription>Odpověď zastaví všechny naplánované follow-upy. Výsledek se použije pro vyhodnocení strategií.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1">
            <Label>Výsledek</Label>
            <NativeSelect value={outcome} onChange={(e) => setOutcome(e.target.value)}>
              {Object.entries(OUTCOME_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <Label>Poznámka</Label>
            <Textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Další krok</Label>
              <Input placeholder="Poslat návrh, call…" value={nextStep} onChange={(e) => setNextStep(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Termín</Label>
              <Input type="datetime-local" value={nextAt} onChange={(e) => setNextAt(e.target.value)} />
            </div>
          </div>
          <DialogFooter><Button type="submit">Uložit</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function FollowUpDialog({ open, onOpenChange, companyId, onDone }: { open: boolean; onOpenChange: (v: boolean) => void; companyId: number; onDone: () => void }) {
  const [days, setDays] = useState(4);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await post(`/companies/${companyId}/outreach/follow-up`, { days });
      toast.success(`Follow-up naplánován za ${days} dní`);
      onOpenChange(false);
      onDone();
    } catch (err) {
      toast.error((err as Error).message);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader><DialogTitle>Naplánovat follow-up</DialogTitle></DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="flex flex-wrap gap-2">
            {[2, 3, 4, 7, 14].map((d) => (
              <Button key={d} type="button" size="sm" variant={d === days ? "default" : "outline"} onClick={() => setDays(d)}>{d} dní</Button>
            ))}
          </div>
          <Input type="number" min={0} max={180} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          <DialogFooter><Button type="submit">Naplánovat</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function OutreachActions({ companyId, messageId, onDone }: { companyId: number; messageId?: number; onDone: () => void }) {
  const [reply, setReply] = useState(false);
  const [fu, setFu] = useState(false);
  async function contacted(kind: "connection_requested" | "message_sent") {
    try {
      const r = await post<{ follow_up_limit_reached: boolean }>(`/companies/${companyId}/outreach/contacted`, { kind, message_id: messageId });
      toast.success(kind === "connection_requested" ? "Žádost o spojení zaznamenána, kontrola za pár dní" : "Označeno jako osloveno, follow-up naplánován");
      if (r.follow_up_limit_reached) toast.info("Limit follow-upů je vyčerpán – další připomínka se neplánuje");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  async function notInterested() {
    const explicit = confirm("Firma výslovně odmítla kontaktování?\n\nOK = přidat na Do Not Contact\nZrušit = jen označit jako nezájem");
    try {
      await post(`/companies/${companyId}/outreach/not-interested`, { explicit_refusal: explicit });
      toast.success(explicit ? "Přidáno na Do Not Contact" : "Označeno jako nezájem");
      onDone();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }
  return (
    <div className="flex flex-wrap gap-2">
      <Button size="sm" variant="outline" onClick={() => contacted("connection_requested")}><UserPlus /> Žádost odeslána</Button>
      <Button size="sm" variant="success" onClick={() => contacted("message_sent")}><CheckCheck /> Označit jako osloveno</Button>
      <Button size="sm" variant="outline" onClick={() => setFu(true)}><CalendarClock /> Follow-up</Button>
      <Button size="sm" variant="outline" onClick={() => setReply(true)}><MessageSquareReply /> Odpověděl</Button>
      <Button size="sm" variant="outline" className="text-red-600" onClick={notInterested}><ThumbsDown /> Nemá zájem</Button>
      <ReplyDialog open={reply} onOpenChange={setReply} companyId={companyId} onDone={onDone} />
      <FollowUpDialog open={fu} onOpenChange={setFu} companyId={companyId} onDone={onDone} />
    </div>
  );
}
