import { NextRequest, NextResponse } from "next/server";
import { appPassword, safeEqual, SESSION_COOKIE, sessionToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

// jednoduchá ochrana proti hádání hesla: max. 10 pokusů za 15 minut z jedné IP
const attempts = new Map<string, { n: number; since: number }>();

function safeNext(next: string | null): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export async function POST(req: NextRequest) {
  const form = await req.formData();
  const password = String(form.get("password") ?? "");
  const next = safeNext(String(form.get("next") ?? "/"));
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim() || "local";
  const now = Date.now();
  const a = attempts.get(ip);
  const entry = a && now - a.since < 15 * 60_000 ? a : { n: 0, since: now };
  const base = req.headers.get("x-forwarded-host")
    ? `${req.headers.get("x-forwarded-proto") ?? "https"}://${req.headers.get("x-forwarded-host")}`
    : req.nextUrl.origin;
  if (entry.n >= 10) {
    return NextResponse.redirect(new URL(`/login?error=limit&next=${encodeURIComponent(next)}`, base), 303);
  }
  const pw = appPassword();
  if (!pw || !safeEqual(password, pw)) {
    attempts.set(ip, { n: entry.n + 1, since: entry.since });
    return NextResponse.redirect(new URL(`/login?error=1&next=${encodeURIComponent(next)}`, base), 303);
  }
  attempts.delete(ip);
  const res = NextResponse.redirect(new URL(next, base), 303);
  res.cookies.set(SESSION_COOKIE, sessionToken(pw), {
    httpOnly: true,
    // na HTTPS SameSite=None, aby přihlášení fungovalo i v rámu stránky huggingface.co
    secure: base.startsWith("https://"),
    sameSite: base.startsWith("https://") ? "none" : "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return res;
}
