"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Ban,
  Bell,
  Bot,
  Gauge,
  Megaphone,
  Search,
  Send,
  Settings,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/api";

const NAV = [
  { href: "/", label: "Přehled", icon: Gauge },
  { href: "/osloveni", label: "Oslovování", icon: Send, hint: "workspace" },
  { href: "/leady", label: "Leady", icon: Users },
  { href: "/follow-up", label: "Follow-upy", icon: Bell, badge: "followups" },
  { href: "/vyhledavani", label: "Vyhledávání", icon: Search },
  { href: "/automatizace", label: "Automatizace", icon: Bot },
  { href: "/kampane", label: "Kampaně", icon: Megaphone },
  { href: "/dnc", label: "Do Not Contact", icon: Ban },
  { href: "/nastaveni", label: "Nastavení", icon: Settings },
];

export function Sidebar() {
  const path = usePathname();
  const { data } = useApi<{ followups_due: number; automation_paused: boolean }>("/dashboard", { refreshInterval: 60000 });
  return (
    <aside className="hidden md:flex w-60 shrink-0 flex-col bg-sidebar text-sidebar-foreground">
      <div className="px-5 py-5">
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-lg bg-primary font-bold text-primary-foreground">P2</div>
          <div>
            <p className="text-sm font-semibold leading-tight">Project Two</p>
            <p className="text-xs opacity-60 leading-tight">Lead Hunter</p>
          </div>
        </div>
      </div>
      <nav className="flex flex-1 flex-col gap-0.5 px-3">
        {NAV.map((n) => {
          const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
          const Icon = n.icon;
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active ? "bg-white/10 font-medium text-white" : "opacity-75 hover:bg-white/5 hover:opacity-100",
              )}
            >
              <Icon className="h-4 w-4" />
              <span className="flex-1">{n.label}</span>
              {n.badge === "followups" && data?.followups_due ? (
                <span className="rounded-full bg-amber-400 px-1.5 text-[10px] font-semibold text-black">{data.followups_due}</span>
              ) : null}
            </Link>
          );
        })}
      </nav>
      <div className="px-5 py-4 text-xs opacity-60">
        {data?.automation_paused ? "⏸ Automatizace pozastavena" : "● Automatizace aktivní"}
      </div>
    </aside>
  );
}

export function MobileNav() {
  const path = usePathname();
  return (
    <nav className="md:hidden flex gap-1 overflow-x-auto border-b bg-card px-2 py-2 scrollbar-thin">
      {NAV.map((n) => {
        const active = n.href === "/" ? path === "/" : path.startsWith(n.href);
        return (
          <Link key={n.href} href={n.href} className={cn("whitespace-nowrap rounded-md px-3 py-1.5 text-sm", active ? "bg-primary text-primary-foreground" : "text-muted-foreground")}>
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}
