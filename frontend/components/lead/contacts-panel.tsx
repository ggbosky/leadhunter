"use client";
import { useState } from "react";
import { toast } from "sonner";
import { BadgeCheck, ExternalLink, Linkedin, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input, NativeSelect, Textarea } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { del, patch, post } from "@/lib/api";
import { CONNECTION_LABELS, fmtDate } from "@/lib/format";
import type { CompanyDetail, Contact } from "@/lib/types";

const SOURCE_LABELS: Record<string, string> = {
  manual: "ručně",
  website: "z webu (neověřeno)",
  ares: "ARES",
  ares_vr: "obchodní rejstřík",
};

type Form = Partial<Contact> & { name: string };

export function ContactDialog({ open, onOpenChange, companyId, contact, onSaved }: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  companyId: number;
  contact?: Contact | null;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<Form>(contact ?? { name: "", role: "", linkedin_url: "", email: "", is_decision_maker: true, is_primary: true });
  const [saving, setSaving] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const body = {
        name: form.name, role: form.role || null, linkedin_url: form.linkedin_url || null, email: form.email || null,
        phone: form.phone || null, is_decision_maker: form.is_decision_maker, is_primary: form.is_primary, verified: true,
        connection_status: form.connection_status, notes: form.notes || null,
      };
      if (contact) await patch(`/contacts/${contact.id}`, body);
      else await post(`/companies/${companyId}/contacts`, body);
      toast.success("Kontakt uložen");
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setSaving(false);
    }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{contact ? "Upravit kontakt" : "Uložit rozhodovací osobu"}</DialogTitle>
          <DialogDescription>Profil vyhledejte ručně na LinkedInu a sem vložte jeho URL.</DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Jméno *</Label>
              <Input required autoFocus value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>Pozice</Label>
              <Input placeholder="Founder, Owner, CEO…" value={form.role ?? ""} onChange={(e) => setForm({ ...form, role: e.target.value })} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>LinkedIn URL</Label>
            <Input placeholder="https://www.linkedin.com/in/…" value={form.linkedin_url ?? ""} onChange={(e) => setForm({ ...form, linkedin_url: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>E-mail</Label>
              <Input value={form.email ?? ""} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>Stav spojení</Label>
              <NativeSelect value={form.connection_status ?? "none"} onChange={(e) => setForm({ ...form, connection_status: e.target.value })}>
                {Object.entries(CONNECTION_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </NativeSelect>
            </div>
          </div>
          <div className="space-y-1">
            <Label>Poznámka</Label>
            <Textarea rows={2} value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
          </div>
          <div className="flex gap-4 text-sm">
            <label className="flex items-center gap-2"><input type="checkbox" checked={!!form.is_decision_maker} onChange={(e) => setForm({ ...form, is_decision_maker: e.target.checked })} /> Rozhodovací osoba</label>
            <label className="flex items-center gap-2"><input type="checkbox" checked={!!form.is_primary} onChange={(e) => setForm({ ...form, is_primary: e.target.checked })} /> Primární kontakt</label>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={saving}>{saving ? "Ukládám…" : "Uložit"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function ContactsPanel({ company, onChanged }: { company: CompanyDetail; onChanged: () => void }) {
  const [editing, setEditing] = useState<Contact | null | undefined>(undefined);
  async function remove(c: Contact) {
    if (!confirm(`Smazat kontakt ${c.name}?`)) return;
    await del(`/contacts/${c.id}`);
    onChanged();
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">Kontakty</p>
        <Button size="sm" onClick={() => setEditing(null)}><Plus /> Přidat</Button>
      </div>
      {company.contacts.length === 0 && <p className="text-sm text-muted-foreground">Zatím žádná rozhodovací osoba. Použijte vyhledávací odkazy níže.</p>}
      <div className="space-y-2">
        {company.contacts.map((c) => (
          <div key={c.id} className="rounded-lg border p-3 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="font-medium">
                  {c.name} {c.verified && <BadgeCheck className="inline h-4 w-4 text-sky-600" />}
                  {c.id === company.best_contact_id && <Badge variant="info" className="ml-1">doporučený</Badge>}
                  {c.do_not_contact && <Badge variant="danger" className="ml-1">DNC</Badge>}
                </p>
                <p className="text-xs text-muted-foreground">{c.role ?? "role neuvedena"} · zdroj: {SOURCE_LABELS[c.source] ?? c.source}</p>
                {c.source_evidence && <p className="text-[11px] text-muted-foreground">{c.source_evidence}</p>}
              </div>
              <div className="flex gap-1">
                <Button size="icon" variant="ghost" onClick={() => setEditing(c)} title="Upravit"><Pencil /></Button>
                <Button size="icon" variant="ghost" onClick={() => remove(c)} title="Smazat"><Trash2 /></Button>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <Badge variant="outline">{CONNECTION_LABELS[c.connection_status] ?? c.connection_status}</Badge>
              {c.linkedin_url ? (
                <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-sky-700 hover:underline dark:text-sky-400">
                  <Linkedin className="h-3 w-3" /> profil
                </a>
              ) : (
                <a href={`https://www.linkedin.com/search/results/people/?keywords=${encodeURIComponent(`${c.name} ${company.name}`)}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-muted-foreground hover:underline">
                  <Search className="h-3 w-3" /> najít na LinkedInu
                </a>
              )}
              {c.email && <span>{c.email}</span>}
              {c.first_contacted_at && <span className="text-muted-foreground">osloveno {fmtDate(c.first_contacted_at)} ({c.contact_attempts}×)</span>}
              {c.next_step && <span className="text-muted-foreground">další krok: {c.next_step} ({fmtDate(c.next_step_at)})</span>}
            </div>
          </div>
        ))}
      </div>
      <div className="space-y-2">
        <p className="text-sm font-medium">LinkedIn – vyhledávání (otevře se ručně)</p>
        <div className="grid gap-1.5">
          {company.linkedin.links.map((l) => (
            <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="flex items-center justify-between rounded-md border px-3 py-1.5 text-xs hover:bg-muted">
              <span className="flex items-center gap-2"><Linkedin className="h-3.5 w-3.5 text-sky-700" /> {l.label}</span>
              <ExternalLink className="h-3 w-3 text-muted-foreground" />
            </a>
          ))}
        </div>
        <p className="text-[11px] text-muted-foreground">
          Aplikace se na LinkedIn nepřihlašuje a nic neodesílá automaticky. Prioritní role: Founder, Co-founder, Owner, CEO, Managing Director, Marketing Manager, E-commerce Manager.
        </p>
      </div>
      {editing !== undefined && (
        <ContactDialog open companyId={company.id} contact={editing} onOpenChange={(v) => !v && setEditing(undefined)} onSaved={onChanged} />
      )}
    </div>
  );
}
