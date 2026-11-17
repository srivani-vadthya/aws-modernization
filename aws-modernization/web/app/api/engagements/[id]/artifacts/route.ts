import { NextResponse } from "next/server";
import { loadEngagement } from "@/lib/store";
import { ISSUE_POLICY_CS, SCHEMA_SQL } from "@/lib/dotnet-sample";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const e = loadEngagement(id);
  if (!e) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const pack = {
    engagement: e.name,
    region: "us-east-1",
    source: e.sourceType,
    scope: e.scopedCapabilityIds,
    requirements: e.requirements,
    backlog: e.backlog,
    target: e.target,
    transformJobs: e.transformJobs,
    failures: e.failures,
    files: {
      "Underwriting.cs": ISSUE_POLICY_CS,
      "schema.sql": SCHEMA_SQL,
    },
  };

  return new NextResponse(JSON.stringify(pack, null, 2), {
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${e.id}-artifacts.json"`,
    },
  });
}
