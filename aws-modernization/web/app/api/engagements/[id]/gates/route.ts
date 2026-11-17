import { NextResponse } from "next/server";
import { loadEngagement } from "@/lib/store";
import { decideGate } from "@/lib/pipeline";
import type { PhaseId } from "@/lib/types";

export const runtime = "nodejs";

export async function POST(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const e = loadEngagement(id);
  if (!e) return NextResponse.json({ error: "Not found" }, { status: 404 });
  const body = (await req.json()) as {
    phase: PhaseId;
    decision: "approved" | "rejected";
    comment?: string;
    actor?: string;
    scopedCapabilityIds?: string[];
  };
  const updated = decideGate(
    e,
    body.phase,
    body.decision,
    body.comment || "",
    body.actor || "architect",
    body.scopedCapabilityIds,
  );
  return NextResponse.json(updated);
}
