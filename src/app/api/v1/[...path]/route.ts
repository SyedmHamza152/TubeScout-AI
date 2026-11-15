import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND = (process.env.BACKEND_URL || "http://127.0.0.1:8321").replace(/\/$/, "");
const HOP_BY_HOP = new Set([
  "connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te",
  "trailer", "transfer-encoding", "upgrade", "host", "content-length",
]);

async function proxy(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const incoming = new URL(request.url);
  incoming.searchParams.delete("XTransformPort");
  const target = `${BACKEND}/api/v1/${path.join("/")}${incoming.search}`;

  const headers = new Headers(request.headers);
  for (const h of HOP_BY_HOP) headers.delete(h);

  const init: RequestInit = { method: request.method, headers, redirect: "manual" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const upstream = await fetch(target, init);
  const out = new Headers(upstream.headers);
  for (const h of HOP_BY_HOP) out.delete(h);
  out.delete("content-encoding");

  return new NextResponse(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: out,
  });
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as PATCH, proxy as DELETE };
