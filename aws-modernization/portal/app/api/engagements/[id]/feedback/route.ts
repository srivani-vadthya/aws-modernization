import { NextResponse } from "next/server";

export const runtime = "nodejs";

const API_BASE = process.env.API_URL ?? "http://localhost:8000";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const body = await req.json();

  const res = await fetch(`${API_BASE}/api/engagements/${id}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  const json = await res.json();
  return NextResponse.json(json, { status: res.status });
}
