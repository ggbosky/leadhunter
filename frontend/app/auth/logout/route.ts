import { NextRequest, NextResponse } from "next/server";
import { SESSION_COOKIE } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const base = req.headers.get("x-forwarded-host")
    ? `${req.headers.get("x-forwarded-proto") ?? "https"}://${req.headers.get("x-forwarded-host")}`
    : req.nextUrl.origin;
  const res = NextResponse.redirect(new URL("/login", base), 303);
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
