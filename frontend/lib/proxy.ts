import { NextRequest } from "next/server";

const BACKEND = process.env.LEADHUNTER_API_URL || "http://127.0.0.1:8000";
const TOKEN = process.env.LEADHUNTER_API_TOKEN || "";

const HOP_HEADERS = new Set(["host", "connection", "content-length", "accept-encoding", "cookie", "authorization"]);

/** Serverový proxy na FastAPI backend – přidá API token, aby nebyl v prohlížeči. */
export async function proxy(req: NextRequest, prefix: string, path: string[]) {
  const url = new URL(`${BACKEND}/${prefix}/${path.map(encodeURIComponent).join("/")}`);
  req.nextUrl.searchParams.forEach((v, k) => url.searchParams.append(k, v));
  const headers = new Headers();
  req.headers.forEach((v, k) => {
    if (!HOP_HEADERS.has(k.toLowerCase())) headers.set(k, v);
  });
  if (TOKEN) headers.set("authorization", `Bearer ${TOKEN}`);
  const init: RequestInit & { duplex?: string } = { method: req.method, headers, redirect: "manual", cache: "no-store" };
  if (!["GET", "HEAD"].includes(req.method)) {
    init.body = await req.arrayBuffer();
  }
  try {
    const res = await fetch(url, init);
    const out = new Headers();
    res.headers.forEach((v, k) => {
      if (!["content-encoding", "transfer-encoding", "connection"].includes(k.toLowerCase())) out.set(k, v);
    });
    return new Response(res.body, { status: res.status, headers: out });
  } catch {
    return Response.json(
      { detail: `Backend není dostupný na ${BACKEND}. Spusťte jej příkazem: cd backend && uvicorn app.main:app` },
      { status: 502 },
    );
  }
}
