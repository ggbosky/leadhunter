import { NextRequest } from "next/server";
import { proxy } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  return proxy(req, "screenshots", path);
}
