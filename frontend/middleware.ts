import { NextRequest, NextResponse } from "next/server";
import { isAuthenticated, SESSION_COOKIE } from "@/lib/auth";

export const config = {
  runtime: "nodejs",
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};

const PUBLIC = ["/login", "/auth/login", "/healthz"];

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  if (PUBLIC.some((p) => pathname === p)) return NextResponse.next();
  if (isAuthenticated(req.cookies.get(SESSION_COOKIE)?.value)) return NextResponse.next();
  if (pathname.startsWith("/api/") || pathname.startsWith("/screenshots/")) {
    return NextResponse.json({ detail: "Nepřihlášeno" }, { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = `?next=${encodeURIComponent(pathname + search)}`;
  return NextResponse.redirect(url);
}
