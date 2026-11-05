export function fmtDate(iso: string | null | undefined, withTime = false) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("cs-CZ", withTime ? { day: "numeric", month: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "numeric", year: "numeric" });
}

export function fmtRelative(iso: string | null | undefined) {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - Date.now()) / 1000;
  const rtf = new Intl.RelativeTimeFormat("cs", { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export function fmtScore(v: number | null | undefined) {
  return v === null || v === undefined ? "—" : Math.round(v).toString();
}

export function fmtCzk(v: number | null | undefined) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("cs-CZ", { style: "currency", currency: "CZK", maximumFractionDigits: 0 }).format(v);
}

export function scoreTone(v: number | null | undefined) {
  if (v === null || v === undefined) return "text-muted-foreground";
  if (v >= 80) return "text-emerald-600 dark:text-emerald-400";
  if (v >= 60) return "text-sky-600 dark:text-sky-400";
  if (v >= 40) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

export function scoreBar(v: number | null | undefined) {
  if (v === null || v === undefined) return "bg-muted-foreground/30";
  if (v >= 80) return "bg-emerald-500";
  if (v >= 60) return "bg-sky-500";
  if (v >= 40) return "bg-amber-500";
  return "bg-red-500";
}

export const CATEGORY_VARIANT: Record<string, "success" | "info" | "warning" | "danger" | "muted"> = {
  priority: "success",
  strong: "info",
  potential: "warning",
  low: "danger",
  insufficient: "muted",
};

export const STATUS_VARIANT: Record<string, "success" | "info" | "warning" | "danger" | "muted" | "secondary"> = {
  new: "muted",
  analyzed: "secondary",
  qualified: "info",
  contacted: "warning",
  replied: "success",
  meeting: "success",
  won: "success",
  lost: "danger",
  disqualified: "danger",
};

export const EVENT_LABELS: Record<string, string> = {
  connection_requested: "Odeslána žádost o spojení",
  connected: "Spojení přijato",
  message_sent: "Odeslána zpráva",
  follow_up_sent: "Odeslán follow-up",
  replied: "Odpověď",
  meeting: "Domluvena schůzka",
  not_interested: "Nemá zájem",
  won: "Získaný klient",
  lost: "Ztraceno",
  note: "Poznámka",
  do_not_contact: "Přidáno na Do Not Contact",
};

export const CONNECTION_LABELS: Record<string, string> = {
  none: "Bez spojení",
  request_sent: "Žádost odeslána",
  connected: "Spojeno",
  ignored: "Ignorováno",
  not_on_linkedin: "Není na LinkedInu",
};

export const JOB_STATUS: Record<string, { label: string; variant: "success" | "info" | "warning" | "danger" | "muted" }> = {
  queued: { label: "Ve frontě", variant: "muted" },
  running: { label: "Běží", variant: "info" },
  done: { label: "Hotovo", variant: "success" },
  failed: { label: "Selhalo", variant: "danger" },
  cancelled: { label: "Zrušeno", variant: "warning" },
};
