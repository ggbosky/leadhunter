"use client";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, NativeSelect } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useMeta } from "@/components/meta-provider";
import { post } from "@/lib/api";

export function AddCompanyDialog({ open, onOpenChange, onCreated }: { open: boolean; onOpenChange: (v: boolean) => void; onCreated?: (id: number) => void }) {
  const meta = useMeta();
  const [form, setForm] = useState({ name: "", website: "", city: "", segment_key: "", ico: "", analyze: true });
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const res = await post<{ company_id: number; created: boolean }>("/companies", {
        ...form,
        segment_key: form.segment_key || null,
        ico: form.ico || null,
        website: form.website || null,
      });
      toast.success(res.created ? "Firma přidána" + (form.analyze ? " a zařazena k analýze" : "") : "Firma už v CRM existuje – záznam aktualizován");
      onOpenChange(false);
      setForm({ name: "", website: "", city: "", segment_key: "", ico: "", analyze: true });
      onCreated?.(res.company_id);
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
          <DialogTitle>Přidat firmu ručně</DialogTitle>
          <DialogDescription>Duplicity se kontrolují podle IČO, domény, názvu a adresy.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1">
            <Label>Název *</Label>
            <Input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </div>
          <div className="space-y-1">
            <Label>Web</Label>
            <Input placeholder="https://…" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Město</Label>
              <Input value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} />
            </div>
            <div className="space-y-1">
              <Label>IČO</Label>
              <Input value={form.ico} onChange={(e) => setForm({ ...form, ico: e.target.value })} />
            </div>
          </div>
          <div className="space-y-1">
            <Label>Obor</Label>
            <NativeSelect value={form.segment_key} onChange={(e) => setForm({ ...form, segment_key: e.target.value })}>
              <option value="">Určit automaticky z webu</option>
              {meta?.segments.map((s) => <option key={s.key} value={s.key}>{s.label} (Tier {s.tier})</option>)}
            </NativeSelect>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={form.analyze} onCheckedChange={(v) => setForm({ ...form, analyze: v })} /> Rovnou analyzovat web
          </label>
          <DialogFooter>
            <Button type="submit" disabled={saving}>{saving ? "Ukládám…" : "Přidat"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
