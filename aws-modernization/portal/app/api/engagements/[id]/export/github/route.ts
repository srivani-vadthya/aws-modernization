import { NextResponse } from "next/server";
import { loadEngagement } from "@/lib/store";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { id } = await ctx.params;
  const e = loadEngagement(id);
  if (!e) return NextResponse.json({ error: "Not found" }, { status: 404 });

  const token = process.env.GITHUB_TOKEN;
  const org = process.env.GITHUB_ORG;
  if (!token || !org) {
    return NextResponse.json({
      pushed: false,
      reason:
        "GITHUB_TOKEN / GITHUB_ORG not configured. Use Download artifacts for the .NET pack.",
      suggestedRepo: `${org || "your-org"}/acme-life-newbusiness`,
    });
  }

  return NextResponse.json({
    pushed: false,
    reason:
      "GitHub create-repo is wired for a later slice; download the artifact pack for this demo.",
  });
}
